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
  makeWASocket,
  useMultiFileAuthState,
  WAMessageStubType,
} from 'baileys';
import qrcode from 'qrcode-terminal';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CONFIG = {
  flaskUrl: (process.env.FLASK_URL || 'http://127.0.0.1:5000').replace(
    /\/$/,
    '',
  ),
  sharedSecret: process.env.WA_SHARED_SECRET || '',
  authFolder: process.env.WA_AUTH_FOLDER || path.join(__dirname, 'auth'),
  helperPort: Number(process.env.WA_HELPER_PORT || 8787),
  reconnectDelay: 5000,
};

let stopping = false;
let sock = null;

// The latest login QR, kept so the helper page can show it.
let currentQr = null;
let currentPairingCode = null;
let isConnected = false;

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
// LOGIN HELPER
// =====================================================

/**
 * Clear a session that was never finished.
 *
 * Asking for a pairing code writes a placeholder identity into the
 * saved credentials. If the process stops before the phone completes
 * the pairing, that half finished session is left behind: Baileys
 * sees an identity and tries to resume a login that never happened,
 * so it never shows a QR again and the sidecar looks stuck.
 *
 * A finished session has `registered` set and a signed identity
 * key. Anything else is discarded so the login starts over.
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

  const finished = creds.registered === true && creds.signedIdentity;

  if (!creds.me || finished) {
    return false;
  }

  console.log(
    'The saved session was never completed, clearing it so a fresh ' +
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

      if (!DELETE_STUB_TYPES.has(stubType)) {
        continue;
      }

      const key = item?.update?.key ?? item?.key ?? {};

      const messageId = key.id ?? item?.key?.id;

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

  clearUnfinishedSession();

  const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authFolder);
  sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: ['RX', 'Chrome', '120.0'],
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
    }

    if (connection === 'open') {
      isConnected = true;
      console.log('Connected to WhatsApp.');
      console.log(`Forwarding events to ${CONFIG.flaskUrl}`);
    }

    if (connection === 'close') {
      isConnected = false;

      const status = lastDisconnect?.error?.output?.statusCode;

      if (status === DisconnectReason.loggedOut) {
        console.error(
          'Logged out. Delete the auth folder and scan the QR again.',
        );
        process.exit(1);
      }

      // A session that was never finished cannot be resumed, so
      // clear it instead of reconnecting into the same broken state.
      clearUnfinishedSession();

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
