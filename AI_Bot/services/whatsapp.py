"""WhatsApp handling.

Three responsibilities:

  1. capture every inbound message the moment it arrives
  2. flag a message as deleted when its revoke event comes in
  3. tell the owner about it, using the per-contact privacy mode

The sidecar sends events in; this module decides what happens.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from config import settings
from database.database import session_scope
from models import Contact, Message, User
from services import gemini, memory, spam_detector


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

async def notify_owner(text: str, reply_markup=None) -> bool:
    """Send a message to the owner on Telegram.

    A fresh Bot is created for each call rather than a shared one:
    this runs inside whatever event loop the caller has, and a Bot
    whose HTTP client was bound to a previous loop cannot be reused.
    """

    if not settings.has_telegram:
        print("TELEGRAM_BOT_TOKEN is not set, skipping notification.")
        return False

    with session_scope() as session:
        chat_id = owner_chat_id(session)

    if not chat_id:
        print("No owner chat id yet, skipping notification.")
        return False

    bot = Bot(token=settings.telegram_bot_token)

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=None,
        )
        return True

    except Exception as error:
        print(f"Could not notify owner: {error}")
        return False

    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass


def _delete_keyboard(message: Message) -> InlineKeyboardMarkup:
    """The Show / Ignore buttons under a delete alert."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👁 Show content",
                    callback_data=f"wa_show:{message.wa_message_id}",
                ),
                InlineKeyboardButton(
                    "🔕 Ignore",
                    callback_data=f"wa_ignore:{message.wa_message_id}",
                ),
            ]
        ]
    )


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
            "body": body,
            "from_me": from_me,
        }


async def process_message_event(payload: dict) -> dict:
    """Capture a message and notify the owner according to the mode."""

    result = handle_message_event(payload)

    if not result.get("ok"):
        return result

    if result.get("from_me"):
        return result

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
        await notify_owner(f"💬 {label}\n\n{body}")
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

    await notify_owner(f"💬 {label}\n\n{summary}")

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
            return {"ok": False, "reason": "message not found"}

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
            "notify": should_notify,
            "body": message.body or "",
            "summary": message.summary or "",
        }


async def process_revoke_event(payload: dict) -> dict:
    """Flag a deleted message and tell the owner about it."""

    result = handle_revoke_event(payload)

    if not result.get("ok"):
        return result

    if not result.get("notify"):
        return result

    label = result.get("contact", "someone")

    await notify_owner(
        f"⚠️ {label} deleted a message.\n\n"
        "Tap Show to see what it said.",
        reply_markup=_delete_keyboard(
            Message(wa_message_id=result["wa_message_id"])
        ),
    )

    return result
