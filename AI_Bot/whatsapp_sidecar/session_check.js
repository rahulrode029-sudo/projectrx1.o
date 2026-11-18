/**
 * Decide whether a saved Baileys auth folder belongs to a real link.
 *
 * Baileys writes `signedIdentityKey` and `me.id` once a phone has
 * completed pairing. Older checks also required `registered === true`,
 * but that flag is not always persisted by every Baileys build. When it
 * was missing, a perfectly good linked session looked "unfinished" and
 * was wiped on the next restart. Keeping this rule in a tiny module
 * makes that distinction easy to test.
 */
export function hasLinkedIdentity(creds) {
  return Boolean(creds && creds.me && creds.me.id && creds.signedIdentityKey);
}
