"""WhatsApp active-session tracking.

The sidecar reports presence transitions; this module turns them into
owner-scoped session rows, web alerts and display-ready strings.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from config import settings
from models import Contact, ContactPreference, PresenceSession
from services import memory
from services.tenancy import current_owner_id

# Sessions closer than this are treated as one window. Phone screen
# locks produce a lot of tiny available/unavailable pairs otherwise.
MERGE_GAP_SECONDS = 120

# Anything shorter than this is noise, not a useful session.
MIN_SESSION_SECONDS = 60


def display_time(value) -> str:
    """Render a stored UTC timestamp in the owner's local time zone."""

    if value is None:
        return ""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    try:
        zone = ZoneInfo(settings.display_timezone)
    except Exception:
        # Windows installs without tzdata still need the owner's time.
        zone = timezone(timedelta(hours=5, minutes=30))

    return value.astimezone(zone).strftime("%d %b %H:%M")


def _as_utc(epoch) -> datetime:
    """Epoch seconds → naive UTC datetime, as stored by SQLAlchemy."""

    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).replace(
        tzinfo=None
    )


def session_data(row: PresenceSession) -> dict:
    """Shape one session for the web page."""

    duration = int(row.duration_seconds or 0)

    return {
        "id": row.id,
        "contact_id": row.contact_id,
        "contact": row.contact.label if row.contact else "unknown",
        "start": display_time(row.started_at),
        "end": display_time(row.ended_at),
        "minutes": max(1, round(duration / 60)),
        "sort_at": row.started_at.isoformat() if row.started_at else "",
    }


def recent_sessions(session, contact_id: int | None = None, limit: int = 30):
    """Sessions for the current owner, newest first."""

    statement = (
        select(PresenceSession)
        .where(PresenceSession.owner_id == current_owner_id())
        .order_by(PresenceSession.started_at.desc())
        .limit(limit)
    )

    if contact_id is not None:
        statement = statement.where(PresenceSession.contact_id == contact_id)

    return list(session.scalars(statement))


def tracked_jids() -> list[str]:
    """JIDs this owner has opted into, for the sidecar watch list."""

    from database.database import session_scope

    with session_scope() as session:
        return list(
            session.scalars(
                select(Contact.jid)
                .join(
                    ContactPreference,
                    ContactPreference.contact_id == Contact.id,
                )
                .where(
                    Contact.owner_id == current_owner_id(),
                    ContactPreference.track_sessions.is_(True),
                )
            )
        )


def set_tracking(contact_id: int, enabled: bool) -> str | None:
    """Turn session tracking on or off. Returns the contact label."""

    from database.database import session_scope

    with session_scope() as session:
        contact = session.get(Contact, contact_id)

        if contact is None or contact.owner_id != current_owner_id():
            return None

        preference = memory.get_preference(session, contact)
        preference.track_sessions = bool(enabled)
        session.commit()

        return contact.label


def record_session(payload: dict) -> dict:
    """Store one `start → end` window and raise the matching web alert."""

    from database.database import session_scope

    try:
        started_at = _as_utc(payload["start_epoch"])
        ended_at = _as_utc(payload["end_epoch"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"ok": False, "reason": "invalid timestamps"}

    if ended_at < started_at:
        ended_at = started_at

    jid = str(payload.get("jid") or "")

    if not jid:
        return {"ok": False, "reason": "missing jid"}

    with session_scope() as session:
        contact = session.scalar(
            select(Contact).where(
                Contact.jid == jid,
                Contact.owner_id == current_owner_id(),
            )
        )

        if contact is None:
            return {"ok": True, "recorded": False, "reason": "unknown contact"}

        preference = memory.get_preference(session, contact)

        if not preference.track_sessions:
            return {"ok": True, "recorded": False, "reason": "not tracked"}

        duplicate = session.scalar(
            select(PresenceSession).where(
                PresenceSession.owner_id == current_owner_id(),
                PresenceSession.contact_id == contact.id,
                PresenceSession.started_at == started_at,
            )
        )

        if duplicate is not None:
            return {"ok": True, "recorded": False, "reason": "duplicate"}

        # A short offline gap is one continuous session as far as the
        # owner is concerned. Extend the previous row instead of adding
        # a second chip a few minutes later.
        previous = session.scalar(
            select(PresenceSession)
            .where(
                PresenceSession.owner_id == current_owner_id(),
                PresenceSession.contact_id == contact.id,
                PresenceSession.ended_at <= started_at,
                PresenceSession.ended_at
                >= started_at - timedelta(seconds=MERGE_GAP_SECONDS),
            )
            .order_by(PresenceSession.ended_at.desc())
            .limit(1)
        )

        if previous is not None:
            row = previous
            row.ended_at = ended_at
            row.duration_seconds = int(
                (ended_at - row.started_at).total_seconds()
            )
            merged = True
        else:
            duration = int((ended_at - started_at).total_seconds())

            if duration < MIN_SESSION_SECONDS:
                return {
                    "ok": True,
                    "recorded": False,
                    "reason": "too short",
                }

            row = PresenceSession(
                owner_id=current_owner_id(),
                contact_id=contact.id,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration,
            )
            session.add(row)
            merged = False

        session.commit()
        data = session_data(row)
        label = data["contact"]

    # Kept outside the session: store_alert opens its own transaction.
    from services import whatsapp as whatsapp_service

    whatsapp_service.store_alert(
        kind="online_session",
        title=f"🟣 {label} was on WhatsApp",
        body=f"{data['start']} → {data['end']} · {data['minutes']} min",
        contact_id=data["contact_id"],
    )

    return {"ok": True, "recorded": True, "merged": merged, **data}
