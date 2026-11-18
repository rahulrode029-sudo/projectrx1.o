"""WhatsApp handling.

Three responsibilities:

  1. capture every inbound message the moment it arrives
  2. flag a message as deleted when its revoke event comes in
  3. write an alert to the database for the web page, using the
     per-contact privacy mode

The sidecar sends events in; this module decides what happens.
Notifications are web-only now - there is no Telegram bot.
"""

import time
from datetime import datetime, timezone

from sqlalchemy import select

from database.database import session_scope
from models import Alert, Contact, Message, User
from services import gemini, memory, spam_detector
from services.tenancy import current_owner_id

# A revoke can overtake the message it refers to. Remember those ids for
# a short while so the message is flagged as soon as it is captured.
PENDING_MINUTES = 10
_pending_deletes: dict[int, dict[str, tuple[str, float]]] = {}


def _remember_pending_delete(owner_id: int, wa_message_id: str, delete_type: str):
    bucket = _pending_deletes.setdefault(owner_id, {})
    bucket[wa_message_id] = (delete_type, time.time() + PENDING_MINUTES * 60)


def _take_pending_delete(owner_id: int, wa_message_id: str) -> str | None:
    bucket = _pending_deletes.get(owner_id, {})
    entry = bucket.pop(wa_message_id, None)

    if entry is None:
        return None

    delete_type, expires_at = entry

    return delete_type if expires_at > time.time() else None


def owner_chat_id(session) -> int | None:
    """The owner's Telegram chat id, learned the first time they write."""

    owner = session.scalar(select(User).where(User.is_owner.is_(True)))

    if owner is None or not owner.platform_id:
        return None

    try:
        return int(owner.platform_id)
    except (TypeError, ValueError):
        return None


def remember_owner(session, chat_id: int, username=None, display_name=None) -> None:
    """Record the owner's chat id so the app can reach them later."""

    owner = session.scalar(select(User).where(User.is_owner.is_(True)))

    if owner is None:
        owner = User(is_owner=True)
        session.add(owner)

    owner.platform = "telegram"
    owner.platform_id = str(chat_id)
    owner.username = username
    owner.display_name = display_name

    session.flush()


# =====================================================
# NOTIFICATION
# =====================================================

def store_alert(
    kind: str,
    title: str,
    body: str,
    contact_id: int | None = None,
    wa_message_id: str | None = None,
) -> int | None:
    """Write an alert for the Messages page.

    Kept synchronous: callers wrap it in `await` only because the old
    Telegram notifier was async. No network call is needed now.
    """

    try:
        with session_scope() as session:
            alert = Alert(
                owner_id=current_owner_id(),
                kind=kind,
                title=title or "",
                body=body or "",
                contact_id=contact_id,
                wa_message_id=wa_message_id,
            )
            session.add(alert)
            session.commit()

            return alert.id

    except Exception as error:
        print(f"Could not store web alert: {error}")
        return None


async def notify_web(
    text: str,
    kind: str = "message",
    title: str = "",
    contact_id: int | None = None,
    wa_message_id: str | None = None,
) -> bool:
    """Async-compatible wrapper used by the event handlers."""

    # The old alert text started with an emoji and label; keep the
    # useful part as the body while the title carries the label.
    body = text

    if "\n\n" in text:
        title, body = text.split("\n\n", 1)

    return store_alert(
        kind=kind,
        title=title,
        body=body,
        contact_id=contact_id,
        wa_message_id=wa_message_id,
    ) is not None


# =====================================================
# EVENT HANDLERS
# =====================================================

def handle_message_event(payload: dict) -> dict:
    """Capture one inbound message.

    Returns a summary of what was done, which the API returns to the
    sidecar so it can be logged.
    """

    chat_jid = payload.get("chat_jid") or ""

    wa_message_id = payload.get("wa_message_id") or ""

    if not wa_message_id:
        return {"ok": False, "reason": "missing wa_message_id"}

    body = payload.get("body") or ""

    from_me = bool(payload.get("from_me"))

    sent_at = payload.get("sent_at")

    if isinstance(sent_at, str):
        try:
            sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        except ValueError:
            sent_at = None

    with session_scope() as session:

        message = memory.store_message(
            session,
            chat_jid=chat_jid,
            wa_message_id=wa_message_id,
            body=body,
            from_me=from_me,
            sender_jid=payload.get("sender_jid"),
            sender_name=payload.get("sender_name"),
            sender_phone=payload.get("sender_phone"),
            sent_at=sent_at,
            message_type=payload.get("message_type") or "text",
            media_type=payload.get("media_type"),
            media_path=payload.get("media_path"),
            is_group=bool(payload.get("is_group")),
        )

        session.commit()

        # The revoke may have arrived before this message. Apply it now
        # so the row is never left looking like an ordinary message.
        pending_delete = _take_pending_delete(current_owner_id(), wa_message_id)

        if pending_delete:
            memory.mark_deleted(session, wa_message_id, pending_delete)
            session.commit()

        contact = message.contact

        mode = "summary"
        label = "someone"

        if contact is not None:
            preference = memory.get_preference(session, contact)
            mode = preference.notify_mode
            label = contact.label

        return {
            "ok": True,
            "message_id": message.id,
            "mode": mode,
            "contact": label,
            "contact_id": message.contact_id,
            "body": body,
            "from_me": from_me,
            "was_deleted": bool(pending_delete),
        }


async def _raise_delete_alert(result: dict) -> None:
    """Write the web alert for a deleted message."""

    if not result.get("notify", True):
        return

    label = result.get("contact", "someone")

    # summary mode keeps the one-line summary; full shows the original
    # text. Either way the alert carries the content so the owner does
    # not need to open a second page to see what was deleted.
    if result.get("mode") == "full":
        content = result.get("body") or result.get("summary") or "(no text)"
    else:
        content = result.get("summary") or result.get("body") or "(no text)"

    await notify_web(
        f"⚠️ {label} deleted a message.\n\n{content}",
        kind="deleted",
        title=f"⚠️ {label} deleted a message",
        contact_id=result.get("contact_id"),
        wa_message_id=result.get("wa_message_id"),
    )


async def process_message_event(payload: dict) -> dict:
    """Capture a message and notify the owner according to the mode."""

    result = handle_message_event(payload)

    if not result.get("ok"):
        return result

    if result.get("from_me"):
        return result

    if result.get("was_deleted"):
        await _raise_delete_alert(
            {
                "contact": result.get("contact", "someone"),
                "contact_id": result.get("contact_id"),
                "wa_message_id": payload.get("wa_message_id"),
                "body": result.get("body") or "",
                "mode": "full",
                "notify": True,
            }
        )

    body = result.get("body") or ""

    if not body.strip():
        return result

    verdict = spam_detector.check_text(body)

    if verdict.is_spam:
        print(f"Spam message from {result['contact']} not surfaced.")
        return result

    mode = result.get("mode", "summary")

    if mode == "silent":
        return result

    label = result.get("contact", "someone")

    if mode == "full":
        await notify_web(
            f"💬 {label}\n\n{body}",
            kind="full",
            title=label,
            contact_id=result.get("contact_id"),
            wa_message_id=payload.get("wa_message_id"),
        )
        return result

    summary = ""

    with session_scope() as session:
        message = session.scalar(
            select(Message).where(
                Message.channel == "whatsapp",
                Message.wa_message_id == payload.get("wa_message_id"),
            )
        )

        if message is not None:
            summary = message.summary or ""

    if not summary:
        summary = gemini.summarize(body)

        with session_scope() as session:
            message = memory.get_message(session, payload.get("wa_message_id"))

            if message is not None:
                memory.set_summary(session, message, summary)
                session.commit()

    await notify_web(
        f"💬 {label}\n\n{summary}",
        kind="summary",
        title=label,
        contact_id=result.get("contact_id"),
        wa_message_id=payload.get("wa_message_id"),
    )

    return result


def handle_revoke_event(payload: dict) -> dict:
    """Flag a deleted message.

    The revoke event carries no content, so the stored row is found by
    its platform message id.
    """

    key = payload.get("key") or {}

    wa_message_id = key.get("id") or payload.get("wa_message_id")

    if not wa_message_id:
        return {"ok": False, "reason": "missing message id"}

    with session_scope() as session:

        message = memory.mark_deleted(
            session, wa_message_id, payload.get("delete_type") or "revoke"
        )

        session.commit()

        if message is None:
            # The revoke overtook the message. Apply it when the message
            # event lands a moment later.
            _remember_pending_delete(
                current_owner_id(),
                wa_message_id,
                payload.get("delete_type") or "revoke",
            )
            print(f"Revoke for {wa_message_id} arrived first; holding it.")
            return {"ok": False, "reason": "message pending", "pending": True}

        contact = message.contact

        label = contact.label if contact else "someone"

        preference = (
            memory.get_preference(session, contact) if contact else None
        )

        should_notify = preference.notify_deleted if preference else True

        return {
            "ok": True,
            "message_id": message.id,
            "wa_message_id": wa_message_id,
            "contact": label,
            "contact_id": message.contact_id,
            "notify": should_notify,
            "mode": preference.notify_mode if preference else "summary",
            "body": message.body or "",
            "summary": message.summary or "",
        }


async def process_revoke_event(payload: dict) -> dict:
    """Flag a deleted message and raise a web alert with its content."""

    result = handle_revoke_event(payload)

    if not result.get("ok"):
        return result

    await _raise_delete_alert(result)

    return result
