import assert from 'node:assert/strict';
import test from 'node:test';

import {
  epochSeconds,
  jidBase,
  learnJidAlias,
  presenceEndEpoch,
  presenceStatus,
  resolveTrackedJid,
} from './presence_check.js';

test('presence status is read from both event shapes', () => {
  assert.equal(presenceStatus({ lastKnownPresence: 'available' }), 'available');
  assert.equal(presenceStatus({ presence: 'unavailable' }), 'unavailable');
  assert.equal(
    presenceStatus({ presence: { lastKnownPresence: 'available' } }),
    'available',
  );
  assert.equal(presenceStatus(null), '');
});

test('an event is matched to the selected JID', () => {
  const tracked = new Set([
    '204453328191567@lid',
    '917666090859@s.whatsapp.net',
  ]);

  assert.equal(
    resolveTrackedJid('917666090859@s.whatsapp.net', tracked),
    '917666090859@s.whatsapp.net',
  );
  assert.equal(
    resolveTrackedJid('917666090859:13@s.whatsapp.net', tracked),
    '917666090859@s.whatsapp.net',
  );
  assert.equal(resolveTrackedJid('999999999999@s.whatsapp.net', tracked), null);
});

test('a learned alias maps a LID event back to the selected contact', () => {
  const tracked = new Set(['917666090859@s.whatsapp.net']);
  const aliases = new Map();

  learnJidAlias(
    '204453328191567@lid',
    '917666090859@s.whatsapp.net',
    aliases,
  );

  assert.equal(
    resolveTrackedJid('204453328191567@lid', tracked, aliases),
    '917666090859@s.whatsapp.net',
  );
  assert.equal(jidBase('917666090859:13@s.whatsapp.net'), '917666090859');
});

test('end time falls back to now when last seen is hidden', () => {
  assert.equal(presenceEndEpoch({ lastSeen: 1000 }, 900, 1200), 1000);
  assert.equal(presenceEndEpoch({}, 900, 1200), 1200);
  assert.equal(presenceEndEpoch({ lastSeen: 800 }, 900, 1200), 1200);
  assert.equal(
    epochSeconds({ toNumber: () => 1000.9 }),
    1000,
  );
});
