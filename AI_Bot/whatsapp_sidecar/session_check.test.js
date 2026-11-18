import assert from 'node:assert/strict';
import test from 'node:test';

import { isFinishedSession } from './session_check.js';

test('a linked WhatsApp session is preserved', () => {
  assert.equal(
    isFinishedSession({
      registered: true,
      me: { id: '918888888888@s.whatsapp.net' },
      signedIdentityKey: { public: 'pub', private: 'priv' },
    }),
    true,
  );
});

test('an abandoned pairing code session is cleared', () => {
  assert.equal(
    isFinishedSession({
      registered: false,
      me: { id: '918888888888@s.whatsapp.net' },
      signedIdentityKey: { public: 'pub', private: 'priv' },
    }),
    false,
  );
});

test('empty or partial credentials are not treated as a link', () => {
  assert.equal(isFinishedSession({}), false);
  assert.equal(isFinishedSession({ me: { id: 'x' } }), false);
  assert.equal(isFinishedSession(null), false);
});
