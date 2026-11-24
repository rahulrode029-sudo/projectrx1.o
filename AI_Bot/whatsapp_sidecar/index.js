/**
 * WhatsApp sidecar.
 *
 * Connects to WhatsApp as a linked device, captures every inbound
 * message and every "delete for everyone", and forwards those events
 * to the Python app, which decides what to store and what to tell
 * the owner about.
 *
 * There is deliberately no business logic here. This process owns the
 * WhatsApp connection and nothing else.
 *
 * Run it with:
 *     npm install
 *     npm start
 *
 * The first run prints a QR code. Scan it with the phone that has the
 * WhatsApp account you want to archive. If the terminal QR is hard to
 * read, open http://127.0.0.1:8787/qr on the computer for a large
 * one, or request a pairing code from the same page.
 */

import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  DisconnectReason,
  fetchLatestBaileysVersion,
  fetchLatestWaWebVersion,
  makeWASocket,
  useMultiFileAuthState,
  WAMessageStubType,
} from 'baileys';
import qrcode from 'qrcode-terminal';
import { hasLinkedIdentity } from './session_check.js';
import {
  epochSeconds,
  learnJidAlias,
  presenceEndEpoch,
  presenceStatus,
  resolveTrackedJid,
} from './presence_check.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CONFIG = {
  flaskUrl: (process.env.FLASK_URL || 'http://127.0.0.1:5000').replace(
    /\/$/,
    '',
  ),
  sharedSecret: process.env.WA_SHARED_SECRET || '',
  // The account this sidecar belongs to. Every event carries its token
  // so the Python app can store the event under the right user.
  userToken: process.env.RX_USER_TOKEN || '',
  userId: process.env.RX_USER_ID || '',
  authFolder: process.env.WA_AUTH_FOLDER || path.join(__dirname, 'auth'),
  helperPort: Number(process.env.WA_HELPER_PORT || 8787),
  reconnectDelay: 5000,
  // The number to link, digits only with the country code. When it
  // is set a pairing code is requested automatically, so the phone
  // can be linked without scanning the QR at all.
  pairingPhone: (process.env.WA_PAIRING_PHONE || '').replace(/\D/g, ''),
};

let stopping = false;
let sock = null;
// A half finished session left by a previous *process* has to go, but
// one that belongs to this process must survive a reconnect: the
// pairing code is tied to the keys in that auth folder, so wiping it
// invalidates the code the user is typing into their phone.
let sessionChecked = false;

// The latest login QR, kept so the helper page can show it.
let currentQr = null;
let currentPairingCode = null;
let isConnected = false;

// Presence is watched only for contacts the owner opted into. The
// watch list comes from the Python app, so the web toggle is the
// single source of truth and one user can never watch another's list.
let trackedJids = new Set();
let presenceTimer = null;
const presenceSessions = new Map();
// Learned from contacts.upsert: WhatsApp may report a person by phone
// JID in one event and by LID in the next.
const jidAliases = new Map();

const PRESENCE_INTERVAL_MS = 8000;
const STALE_AVAILABLE_SECONDS = 300;
const MIN_SESSION_SECONDS = 60;

// =====================================================
// POSTING EVENTS
// =====================================================

/**
 * Send one event to the Python app.
 */
async function postEvent(payload) {
  try {
    const response = await fetch(`${CONFIG.flaskUrl}/wa/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-WA-Secret': CONFIG.sharedSecret,
        'X-RX-Token': CONFIG.userToken,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.error(
        `[event] ${payload.type} rejected with HTTP ${response.status}`,
      );
      return false;
    }

    return true;
  } catch (error) {
    console.error(`[event] ${payload.type} could not be sent:`, error.message);
    return false;
  }
}

// =====================================================
// PRESENCE / ACTIVE SESSIONS
// =====================================================

/**
 * Ask the app which contacts this account is tracking. Fetching the
 * list every tick means a toggle in the web UI takes effect without
 * restarting the sidecar.
 */
async function refreshTrackedJids() {
  if (!isConnected || !sock) {
    return;
  }

  try {
    const response = await fetch(`${CONFIG.flaskUrl}/wa/tracked`, {
      headers: {
        'X-WA-Secret': CONFIG.sharedSecret,
        'X-RX-Token': CONFIG.userToken,
      },
    });

    if (!response.ok) {
      return;
    }

    const data = await response.json();
    const next = new Set(data.jids || []);
    const before = [...trackedJids].sort().join(',');

    // Drop local state for anything the owner stopped tracking.
    for (const jid of trackedJids) {
      if (!next.has(jid)) {
        presenceSessions.delete(jid);
      }
    }

    trackedJids = next;

    const after = [...trackedJids].sort().join(',');

    if (before !== after) {
      console.log(`[presence] watching ${trackedJids.size} selected contacts`);
    }

    // Subscriptions expire after roughly ten seconds, so renew them
    // on every tick for the contacts that are still selected.
    for (const jid of trackedJids) {
      try {
        await sock.presenceSubscribe(jid);
      } catch (error) {
        console.error(`[presence] cannot watch ${jid}: ${error.message}`);
      }
    }
  } catch (error) {
    console.error('[presence] could not load the watch list:', error.message);
  }
}

/**
 * Finish a session and forward the time window. Very short blips are
 * dropped here and merged server-side when they are close together.
 */
function closePresenceSession(jid, endEpoch, state) {
  if (!state || !state.start) {
    return;
  }

  const end = endEpoch || Math.floor(Date.now() / 1000);
  const duration = end - state.start;

  if (duration >= MIN_SESSION_SECONDS) {
    console.log(
      `[presence] session ${jid}: ${state.start} → ${end} (${duration}s)`,
    );
    void postEvent({
      type: 'presence_session',
      jid,
      start_epoch: state.start,
      end_epoch: end,
    });
  } else {
    console.log(`[presence] skipped ${duration}s blip for ${jid}`);
  }

  presenceSessions.set(jid, { start: null, lastAvailable: null });
}

/**
 * An `unavailable` event does not always arrive (phone killed, network
 * drop). Treat a long silence after the last available heartbeat as
 * the end of the session.
 */
function finalizeStaleSessions() {
  const now = Math.floor(Date.now() / 1000);

  for (const [jid, state] of presenceSessions.entries()) {
    if (
      state.start &&
      state.lastAvailable &&
      now - state.lastAvailable > STALE_AVAILABLE_SECONDS
    ) {
      closePresenceSession(jid, state.lastAvailable, state);
    }
  }
}

function onPresenceUpdate({ presences }) {
  for (const [rawJid, data] of Object.entries(presences || {})) {
    const status = presenceStatus(data);

    // Typing/composing updates are frequent and are not active windows.
    if (status !== 'available' && status !== 'unavailable') {
      continue;
    }

    // Baileys may use a device suffix or the other identifier family.
    // Always post the JID the owner actually selected in the web UI.
    const jid = resolveTrackedJid(rawJid, trackedJids, jidAliases);

    if (!jid || !data) {
      console.log(`[presence] ignored ${rawJid} (${status}) - not selected`);
      continue;
    }

    console.log(
      `[presence] ${jid} ${status}${rawJid !== jid ? ` (via ${rawJid})` : ''}`,
    );

    const state =
      presenceSessions.get(jid) || { start: null, lastAvailable: null };

    const now = Math.floor(Date.now() / 1000);

    if (status === 'available') {
      if (!state.start) {
        state.start = now;
      }

      state.lastAvailable = now;
    } else {
      closePresenceSession(jid, presenceEndEpoch(data, state.start, now), state);
      continue;
    }

    presenceSessions.set(jid, state);
  }
}

async function presenceTick() {
  if (stopping) {
    return;
  }

  await refreshTrackedJids();
  finalizeStaleSessions();
}

function startPresenceWatch() {
  if (presenceTimer) {
    return;
  }

  void presenceTick();
  presenceTimer = setInterval(() => void presenceTick(), PRESENCE_INTERVAL_MS);
}

function stopPresenceWatch() {
  if (presenceTimer) {
    clearInterval(presenceTimer);
    presenceTimer = null;
  }

  presenceSessions.clear();
}

// =====================================================
// LOGIN HELPER
// =====================================================

/**
 * Find the WhatsApp Web version to connect with.
 *
 * The version bundled with Baileys goes stale, and a stale client
 * revision blocks linking. Ask WhatsApp for the current one and fall
 * back to the bundled list if that cannot be reached.
 */
async function resolveWebVersion() {
  try {
    const latest = await fetchLatestWaWebVersion();

    if (latest && latest.version) {
      console.log(`WhatsApp Web version: ${latest.version.join('.')}`);
      return latest.version;
    }
  } catch (error) {
    console.log(
      `Could not fetch the WhatsApp Web version: ${error.message}`,
    );
  }

  try {
    const fallback = await fetchLatestBaileysVersion();

    if (fallback && fallback.version) {
      console.log(
        `Falling back to the Baileys bundled version: ` +
          `${fallback.version.join('.')}`,
      );
      return fallback.version;
    }
  } catch (error) {
    console.log(`Could not fetch the Baileys version: ${error.message}`);
  }

  console.log('Using whatever version Baileys defaults to.');

  return undefined;
}

/**
 * Clear a session that was never finished.
 *
 * Asking for a pairing code writes a placeholder identity into the
 * saved credentials. If the process stops before the phone completes
 * the pairing, that half finished session is left behind: Baileys
 * sees an identity and tries to resume a login that never happened,
 * so it never shows a QR again and the sidecar looks stuck.
 *
 * A real link has a signed identity key and a `me.id`. Anything else
 * is discarded so the login starts over. The `registered` flag is not
 * reliable enough to use here.
 */
function clearUnfinishedSession() {
  const credsPath = path.join(CONFIG.authFolder, 'creds.json');

  if (!fs.existsSync(credsPath)) {
    return false;
  }

  let creds;

  try {
    creds = JSON.parse(fs.readFileSync(credsPath, 'utf-8'));
  } catch (error) {
    console.log('The saved session could not be read, clearing it.');
    creds = {};
  }

  if (hasLinkedIdentity(creds)) {
    return false;
  }

  console.log(
    'The saved session has no linked identity, clearing it so a fresh ' +
      'QR code is shown.',
  );

  fs.rmSync(CONFIG.authFolder, { recursive: true, force: true });
  fs.mkdirSync(CONFIG.authFolder, { recursive: true });

  return true;
}

/**
 * Ask WhatsApp for an eight character pairing code.
 *
 * This is the alternative to scanning the QR. The phone goes to
 * Linked devices, chooses "Link with phone number instead", types
 * the number and then types this code.
 */
async function requestPairingCode(phone) {
  const digits = String(phone || '').replace(/\D/g, '');

  if (digits.length < 8) {
    throw new Error('the phone number needs a country code');
  }

  const code = await sock.requestPairingCode(digits);

  currentPairingCode = code;

  console.log('');
  console.log('  Pairing code: ' + code);
  console.log('  For number:   +' + digits);
  console.log('');
  console.log('  On the phone: WhatsApp > Settings > Linked devices >');
  console.log('  Link a Device > Link with phone number instead');
  console.log('');

  return code;
}

/**
 * A tiny local server so the QR and the pairing code can be shown in
 * a browser, which is much easier to scan than a terminal.
 *
 * This is started exactly once. The socket is rebuilt whenever the
 * connection drops, and the helper must not be rebuilt with it or the
 * second bind fails with EADDRINUSE and takes the process down.
 */
function startHelperServer() {
  const server = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Content-Type', 'application/json');

    const send = (status, payload) => {
      res.statusCode = status;
      res.end(JSON.stringify(payload));
    };

    if (req.method === 'GET' && req.url === '/qr') {
      send(200, {
        qr: currentQr,
        pairingCode: currentPairingCode,
        connected: isConnected,
      });
      return;
    }

    if (req.method === 'POST' && req.url === '/pairing') {
      let body = '';

      req.on('data', (chunk) => {
        body += chunk;
      });

      req.on('end', async () => {
        try {
          const parsed = JSON.parse(body || '{}');
          const code = await requestPairingCode(parsed.phone);
          send(200, { pairingCode: code });
        } catch (error) {
          send(500, { error: error.message });
        }
      });

      return;
    }

    /**
     * Send a short text through this account's WhatsApp. Used by the
     * forgot-password flow, which falls back to SMS when this fails.
     */
    if (req.method === 'POST' && req.url === '/send') {
      if (
        !CONFIG.userToken ||
        req.headers['x-rx-token'] !== CONFIG.userToken
      ) {
        send(401, { error: 'unauthorised' });
        return;
      }

      let body = '';

      req.on('data', (chunk) => {
        body += chunk;
      });

      req.on('end', async () => {
        try {
          const parsed = JSON.parse(body || '{}');
          const to = String(parsed.to || '');
          const text = String(parsed.text || '');

          if (!to || !text || !sock || !isConnected) {
            send(503, { error: 'WhatsApp is not ready' });
            return;
          }

          await sock.sendMessage(to, { text });
          send(200, { ok: true });
        } catch (error) {
          send(500, { error: error.message });
        }
      });

      return;
    }

    send(404, { error: 'not found' });
  });

  server.on('error', (error) => {
    if (error.code === 'EADDRINUSE') {
      console.error(
        `Port ${CONFIG.helperPort} is already in use. Another sidecar ` +
          `is probably still running. Close it, or set ` +
          `WA_HELPER_PORT to a different port.`,
      );
    } else {
      console.error('The login helper server failed:', error.message);
    }

    process.exit(1);
  });

  server.listen(CONFIG.helperPort, '127.0.0.1', () => {
    console.log(
      `Login helper: http://127.0.0.1:${CONFIG.helperPort}/qr`,
    );
  });
}

// =====================================================
// READING A MESSAGE
// =====================================================

/**
 * Pull the readable text and media kind out of a WhatsApp message.
 *
 * WhatsApp has many message shapes; this covers the ones that
 * actually carry something worth archiving.
 */
function readMessage(message) {
  const content = message.message || {};

  if (content.conversation) {
    return { body: content.conversation, type: 'text' };
  }

  if (content.extendedTextMessage?.text) {
    return { body: content.extendedTextMessage.text, type: 'text' };
  }

  if (content.imageMessage) {
    return { body: content.imageMessage.caption || '', type: 'image' };
  }

  if (content.videoMessage) {
    return { body: content.videoMessage.caption || '', type: 'video' };
  }

  if (content.audioMessage) {
    return { body: content.audioMessage.caption || '', type: 'audio' };
  }

  if (content.documentMessage) {
    return { body: content.documentMessage.caption || '', type: 'document' };
  }

  if (content.stickerMessage) {
    return { body: '', type: 'sticker' };
  }

  if (content.contactMessage) {
    return {
      body: content.contactMessage.displayName || '',
      type: 'contact',
    };
  }

  if (content.locationMessage) {
    return { body: '', type: 'location' };
  }

  if (content.viewOnceMessage) {
    return { body: '', type: 'view_once' };
  }

  if (content.viewOnceMessageV2) {
    return { body: '', type: 'view_once' };
  }

  if (content.pollCreationMessage) {
    return {
      body: content.pollCreationMessage.name || '',
      type: 'poll',
    };
  }

  if (content.reactionMessage) {
    return { body: '', type: 'reaction' };
  }

  if (content.protocolMessage) {
    // A revoke or an edit arriving as a protocol message. These are
    // handled by the messages.update listener instead.
    return { body: '', type: 'protocol' };
  }

  return { body: '', type: 'unknown' };
}

/**
 * The sender of a message. In a group this is the participant, not
 * the chat itself.
 */
function senderOf(message) {
  const participant = message.participant || message.key?.participant;

  return participant || message.key?.remoteJid || '';
}

/**
 * True when the chat is a group.
 */
function isGroup(jid) {
  return typeof jid === 'string' && jid.endsWith('@g.us');
}

// =====================================================
// EVENT HANDLERS
// =====================================================

/**
 * A new message arrived. Store it before anything else happens, so
 * it is captured even if the owner never looks at it.
 */
async function onMessagesUpsert({ messages }) {
  for (const message of messages) {
    try {
      if (message.key?.fromMe) {
        continue;
      }

      const { body, type } = readMessage(message);

      const remoteJid = message.key?.remoteJid || '';

      await postEvent({
        type: 'message',
        chat_jid: remoteJid,
        wa_message_id: message.key?.id,
        body,
        message_type: type,
        from_me: false,
        sender_jid: senderOf(message),
        sender_name: message.pushName || null,
        sender_phone: null,
        is_group: isGroup(remoteJid),
        sent_at: message.messageTimestamp
          ? new Date(Number(message.messageTimestamp) * 1000).toISOString()
          : null,
      });
    } catch (error) {
      console.error('[message] failed to forward:', error.message);
    }
  }
}

/**
 * The stub types that mean the message is gone.
 *
 * REVOKE is an ordinary "delete for everyone". ADMIN_REVOKE is a
 * group admin deleting someone else's message, which is worth
 * catching too.
 */
const DELETE_STUB_TYPES = new Set([
  WAMessageStubType.REVOKE,
  WAMessageStubType.ADMIN_REVOKE,
]);

/**
 * A message was edited or deleted.
 *
 * The delete event carries no content at all, only the id of the
 * message it refers to. The Python side looks that id up in the
 * database, which is why every message is stored the moment it
 * arrives.
 */
async function onMessagesUpdate(updates) {
  for (const item of updates) {
    try {
      // The stub type sits inside `update` on this Baileys version.
      // The flat shape is checked too so a version bump does not
      // silently stop delete detection.
      const stubType =
        item?.update?.messageStubType ?? item?.messageStubType;

      if (stubType === undefined || stubType === null) {
        continue;
      }

      const key = item?.update?.key ?? item?.key ?? {};
      const messageId = key.id ?? item?.key?.id;

      // Keep this visible: a missed revoke is otherwise invisible and
      // makes the archive look like it ignored a deletion.
      console.log(
        `[update] stub=${stubType} id=${messageId || '(none)'} ` +
          `delete=${DELETE_STUB_TYPES.has(stubType)}`,
      );

      if (!DELETE_STUB_TYPES.has(stubType)) {
        continue;
      }

      if (!messageId) {
        continue;
      }

      await postEvent({
        type: 'revoke',
        delete_type:
          stubType === WAMessageStubType.ADMIN_REVOKE
            ? 'admin_revoke'
            : 'revoke',
        key: {
          id: messageId,
          remoteJid: key.remoteJid ?? null,
          participant: key.participant ?? null,
          fromMe: key.fromMe ?? false,
        },
      });
    } catch (error) {
      console.error('[revoke] failed to forward:', error.message);
    }
  }
}

/**
 * A bulk delete, or "delete for me".
 */
async function onMessagesDelete(event) {
  try {
    const keys = event?.keys || [];

    if (!keys.length) {
      return;
    }

    console.log(`[delete] ${keys.length} message key(s)`);

    await postEvent({
      type: 'delete',
      keys: keys.map((key) => ({
        id: key.id,
        remoteJid: key.remoteJid ?? null,
        participant: key.participant ?? null,
        fromMe: key.fromMe ?? false,
      })),
    });
  } catch (error) {
    console.error('[delete] failed to forward:', error.message);
  }
}

/**
 * Contact details.
 */
async function onContactsUpsert(contacts) {
  for (const contact of contacts) {
    try {
      // A person can arrive with both a phone JID and a LID. Remember
      // the pair so presence events can be matched to the selected JID.
      const lid = contact.lid || contact.id;
      const phoneJid = contact.phoneNumber
        ? `${contact.phoneNumber}@s.whatsapp.net`
        : contact.id;

      if (lid && phoneJid) {
        learnJidAlias(lid, phoneJid, jidAliases);
      }

      await postEvent({
        type: 'contact',
        jid: contact.id,
        push_name: contact.name || null,
        phone: contact.phoneNumber || contact.verifiedName || null,
      });
    } catch (error) {
      console.error('[contact] failed to forward:', error.message);
    }
  }
}

// =====================================================
// MAIN
// =====================================================

async function startSocket() {
  if (!CONFIG.sharedSecret) {
    console.error(
      'WA_SHARED_SECRET is not set. Copy it from ../.env into this ' +
        "process's environment before starting.",
    );
    process.exit(1);
  }

  if (!sessionChecked) {
    clearUnfinishedSession();
    sessionChecked = true;
  }

  const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authFolder);

  const version = await resolveWebVersion();

  sock = makeWASocket({
    auth: state,
    browser: ['RX', 'Chrome', '120.0'],
    ...(version ? { version } : {}),
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQr = qr;

      console.log('\nScan this QR code with WhatsApp on your phone:\n');
      qrcode.generate(qr, { small: true });
      console.log(
        `\nPrefer a bigger code? Open http://127.0.0.1:${CONFIG.helperPort}/qr\n`,
      );

      // The QR event also fires while a pairing code is possible, so
      // this is the right moment to ask for one. Requesting it here
      // means the socket is in the registration state it needs.
      if (CONFIG.pairingPhone && !currentPairingCode) {
        try {
          await requestPairingCode(CONFIG.pairingPhone);
        } catch (error) {
          console.log(
            `Could not request a pairing code: ${error.message}`,
          );
        }
      }
    }

    if (connection === 'open') {
      isConnected = true;
      console.log('Connected to WhatsApp.');
      console.log(`Forwarding events to ${CONFIG.flaskUrl}`);
      startPresenceWatch();
    }

    if (connection === 'close') {
      isConnected = false;
      stopPresenceWatch();

      // Keep the code on screen while reconnecting. The keys that
      // back it live in the auth folder, which is now preserved, so
      // the same code stays usable and the user can keep entering it.
      const status = lastDisconnect?.error?.output?.statusCode;

      if (status === DisconnectReason.loggedOut) {
        // A rejected login must not take the sidecar down for good.
        // Start over with a clean session and a fresh QR/code.
        console.log('Logged out. Clearing the session and starting over.');
        trackedJids.clear();
        fs.rmSync(CONFIG.authFolder, { recursive: true, force: true });
        fs.mkdirSync(CONFIG.authFolder, { recursive: true });
        currentPairingCode = null;

        if (!stopping) {
          setTimeout(() => startSocket(), CONFIG.reconnectDelay);
        }

        return;
      }

      // Preserve the auth folder here. Only a previous process's
      // abandoned session is cleared, at startup.
      if (!stopping) {
        console.log(`Disconnected (${status}). Reconnecting shortly...`);
        setTimeout(() => startSocket(), CONFIG.reconnectDelay);
      }
    }
  });

  sock.ev.on('messages.upsert', onMessagesUpsert);
  sock.ev.on('messages.update', onMessagesUpdate);
  sock.ev.on('messages.delete', onMessagesDelete);
  sock.ev.on('contacts.upsert', onContactsUpsert);
  sock.ev.on('presence.update', onPresenceUpdate);
}

process.on('SIGINT', async () => {
  console.log('\nStopping...');
  stopping = true;

  try {
    if (sock) {
      await sock.end(undefined);
    }
  } catch (error) {
    // Nothing to do if the socket is already gone.
  }

  process.exit(0);
});

// The helper is started once for the life of the process. The socket
// is rebuilt on every reconnect, but the helper must not be, or the
// second bind to the port fails and the process dies.
startHelperServer();

startSocket().catch((error) => {
  console.error('Sidecar failed to start:', error);
  process.exit(1);
});
