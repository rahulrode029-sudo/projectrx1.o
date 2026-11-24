/**
 * Testable helpers for Baileys presence events.
 *
 * The sidecar deliberately keeps no business logic, but deciding which
 * JID an event belongs to is fiddly: WhatsApp may add a device suffix,
 * report a LID instead of a phone number, or omit `lastSeen` when the
 * contact hides their last seen. These small rules make that behaviour
 * explicit and testable without starting a WhatsApp connection.
 */

/**
 * Baileys occasionally passes Long-like values. Normalise them to
 * epoch seconds, or null when the value cannot be trusted.
 */
export function epochSeconds(value) {
  if (value === null || value === undefined) {
    return null;
  }

  const number =
    typeof value === 'object' && typeof value.toNumber === 'function'
      ? value.toNumber()
      : Number(value);

  return Number.isFinite(number) ? Math.floor(number) : null;
}

/** Strip `@s.whatsapp.net`, `@lid` and device suffixes. */
export function jidBase(jid) {
  return String(jid || '').split('@')[0].split(':')[0];
}

/**
 * Remember that two identifiers belong to the same person.
 * `contacts.upsert` sometimes exposes both the phone JID and the LID.
 */
export function learnJidAlias(left, right, aliases) {
  const a = jidBase(left);
  const b = jidBase(right);

  if (!a || !b || a === b) {
    return;
  }

  aliases.set(a, String(right));
  aliases.set(b, String(left));
}

/**
 * Map an incoming presence event to the JID the owner selected in the
 * web UI. Exact matches win; device suffixes and learned aliases follow.
 */
export function resolveTrackedJid(jid, trackedJids, aliases = new Map()) {
  if (trackedJids.has(jid)) {
    return jid;
  }

  const base = jidBase(jid);

  if (!base) {
    return null;
  }

  for (const tracked of trackedJids) {
    if (jidBase(tracked) === base) {
      return tracked;
    }
  }

  const alias = aliases.get(base);
  return alias && trackedJids.has(alias) ? alias : null;
}

/** Read `available` / `unavailable` from the several event shapes. */
export function presenceStatus(data) {
  if (!data || typeof data !== 'object') {
    return '';
  }

  if (data.lastKnownPresence) {
    return data.lastKnownPresence;
  }

  if (data.presence && data.presence.lastKnownPresence) {
    return data.presence.lastKnownPresence;
  }

  return data.presence || '';
}

/**
 * Prefer the time WhatsApp reports, but fall back to the event time.
 * Hidden last-seen privacy means `lastSeen` is often absent.
 */
export function presenceEndEpoch(data, start, now) {
  const reported = epochSeconds(data && data.lastSeen);
  return reported && start && reported >= start ? reported : now;
}
