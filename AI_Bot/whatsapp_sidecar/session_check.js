/**
 * Decide whether a saved Baileys auth folder belongs to a finished link.
 *
 * The field Baileys writes after a successful pairing is
 * `signedIdentityKey`. An earlier check looked for `signedIdentity`,
 * which never exists, so every previously linked session looked
 * "unfinished" and was wiped on the next start. Keeping this rule in a
 * tiny module makes that distinction easy to test.
 */
export function isFinishedSession(creds) {
  return Boolean(
    creds && creds.registered === true && creds.signedIdentityKey,
  );
}
