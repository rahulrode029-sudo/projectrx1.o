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
 * WhatsApp account you want to archive.
 */

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
  reconnectDelay: 5000,
};

let stopping = false;

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

async function start() {
  if (!CONFIG.sharedSecret) {
    console.error(
      'WA_SHARED_SECRET is not set. Copy it from ../.env into this ' +
        "process's environment before starting.",
    );
    return;
  }

  const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authFolder);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: ['RX', 'Chrome', '120.0'],
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\nScan this QR code with WhatsApp on your phone:\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'open') {
      console.log('Connected to WhatsApp.');
      console.log(`Forwarding events to ${CONFIG.flaskUrl}`);
    }

    if (connection === 'close') {
      const status = lastDisconnect?.error?.output?.statusCode;

      if (status === DisconnectReason.loggedOut) {
        console.error(
          'Logged out. Delete the auth folder and scan the QR again.',
        );
        process.exit(1);
      }

      if (!stopping) {
        console.log(`Disconnected (${status}). Reconnecting shortly...`);
        setTimeout(() => start(), CONFIG.reconnectDelay);
      }
    }
  });

  sock.ev.on('messages.upsert', onMessagesUpsert);
  sock.ev.on('messages.update', onMessagesUpdate);
  sock.ev.on('messages.delete', onMessagesDelete);
  sock.ev.on('contacts.upsert', onContactsUpsert);

  process.on('SIGINT', async () => {
    console.log('\nStopping...');
    stopping = true;
    try {
      await sock.end(undefined);
    } catch (error) {
      // Nothing to do if the socket is already gone.
    }
    process.exit(0);
  });
}

start().catch((error) => {
  console.error('Sidecar failed to start:', error);
  process.exit(1);
});
