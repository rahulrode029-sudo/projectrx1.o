import assert from 'node:assert/strict';
import test from 'node:test';

import { hasLinkedIdentity } from './session_check.js';

test('a linked WhatsApp session is preserved', () => {
  assert.equal(
    hasLinkedIdentity({
      registered: true,
      me: { id: '918888888888@s.whatsapp.net' },
      signedIdentityKey: { public: 'pub', private: 'priv' },
    }),
    true,
  );
});

test('a missing registered flag never wipes a linked session', () => {
  assert.equal(
    hasLinkedIdentity({
      registered: false,
      me: { id: '918888888888@s.whatsapp.net' },
      signedIdentityKey: { public: 'pub', private: 'priv' },
    }),
    true,
  );
});

test('empty or partial credentials are not treated as a link', () => {
  assert.equal(hasLinkedIdentity({}), false);
  assert.equal(hasLinkedIdentity({ me: { id: 'x' } }), false);
  assert.equal(
    hasLinkedIdentity({ signedIdentityKey: { public: 'pub' } }),
    false,
  );
  assert.equal(hasLinkedIdentity(null), false);
});
