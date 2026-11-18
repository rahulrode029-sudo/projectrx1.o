"""Storing, finding and summarising captured messages.

This is the layer that knows what the bot has seen. The WhatsApp
sidecar calls into it for every event; the Telegram commands query it.
"""

import math
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database.database import session_scope
from services.tenancy import current_owner_id
from models import (
    DEFAULT_NOTIFY_MODE,
    Contact,
    ContactPreference,
    Conversation,
    Message,
)


def _now():
    return datetime.now(timezone.utc)


def _as_naive_utc(value):
    """SQLite stores naive datetimes, so normalise everything to naive UTC."""

    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


# =====================================================
# CONTACTS AND CONVERSATIONS
# =====================================================

def get_or_create_contact(
    session: Session,
    jid: str,
    push_name=None,
    phone=None,
) -> Contact:
    """Find a contact by JID, or create it, for the current account."""

    owner_id = current_owner_id()

    contact = session.scalar(
        select(Contact).where(Contact.jid == jid, Contact.owner_id == owner_id)
    )

    if contact is None:

        contact = Contact(
            owner_id=owner_id,
            jid=jid,
            push_name=push_name,
            phone=phone,
            last_seen_at=_now(),
        )

        session.add(contact)
        session.flush()

        session.add(
            ContactPreference(
                contact_id=contact.id,
                notify_mode=DEFAULT_NOTIFY_MODE,
            )
        )

    else:
        if push_name and contact.push_name != push_name:
            contact.push_name = push_name

        if phone and not contact.phone:
            contact.phone = phone

        contact.last_seen_at = _now()

    session.flush()

    return contact


def get_or_create_conversation(
    session: Session,
    chat_jid: str,
    contact: Contact | None = None,
    is_group: bool = False,
    title: str | None = None,
) -> Conversation:
    """Find the chat thread for a JID, or create it."""

    owner_id = current_owner_id()

    conversation = session.scalar(
        select(Conversation).where(
            Conversation.channel == "whatsapp",
            Conversation.chat_jid == chat_jid,
            Conversation.owner_id == owner_id,
        )
    )

    if conversation is None:

        conversation = Conversation(
            owner_id=owner_id,
            channel="whatsapp",
            chat_jid=chat_jid,
            contact_id=contact.id if contact else None,
            is_group=is_group,
            title=title,
            last_activity_at=_now(),
        )

        session.add(conversation)
        session.flush()

    else:
        conversation.last_activity_at = _now()

        if contact and not conversation.contact_id:
            conversation.contact_id = contact.id

    session.flush()

    return conversation


# =====================================================
# MESSAGES
# =====================================================

def store_message(
    session: Session,
    chat_jid: str,
    wa_message_id: str,
    body: str = "",
    from_me: bool = False,
    sender_jid: str | None = None,
    sender_name: str | None = None,
    sender_phone: str | None = None,
    sent_at: datetime | None = None,
    message_type: str = "text",
    media_type: str | None = None,
    media_path: str | None = None,
    is_group: bool = False,
) -> Message:
    """Capture one message.

    Safe to call twice with the same platform id: the existing row is
    returned rather than duplicated.
    """

    owner_id = current_owner_id()

    existing = session.scalar(
        select(Message).where(
            Message.channel == "whatsapp",
            Message.wa_message_id == wa_message_id,
            Message.owner_id == owner_id,
        )
    )

    if existing is not None:
        return existing

    contact = None

    if not from_me and sender_jid:
        contact = get_or_create_contact(
            session, sender_jid, sender_name, sender_phone
        )

    conversation = get_or_create_conversation(
        session, chat_jid, contact=contact, is_group=is_group
    )

    message = Message(
        owner_id=owner_id,
        channel="whatsapp",
        conversation_id=conversation.id,
        contact_id=contact.id if contact else None,
        wa_message_id=wa_message_id,
        from_me=from_me,
        sender_jid=sender_jid,
        body=body or "",
        message_type=message_type,
        media_type=media_type,
        media_path=media_path,
        sent_at=_as_naive_utc(sent_at) or _as_naive_utc(_now()),
    )

    session.add(message)
    session.flush()

    return message


def mark_deleted(
    session: Session,
    wa_message_id: str,
    delete_type: str = "revoke",
) -> Message | None:
    """Flag a stored message as deleted.

    This is the join point for the WhatsApp REVOKE event. The event
    carries no content of its own, so the row is located by the
    platform message id and flagged in place.
    """

    message = session.scalar(
        select(Message).where(
            Message.channel == "whatsapp",
            Message.wa_message_id == wa_message_id,
            Message.owner_id == current_owner_id(),
        )
    )

    if message is None:
        return None

    if not message.is_deleted:
        message.is_deleted = True
        message.deleted_at = _as_naive_utc(_now())
        message.delete_type = delete_type

        session.flush()

    return message


def get_message(session: Session, wa_message_id: str) -> Message | None:
    return session.scalar(
        select(Message).where(
            Message.channel == "whatsapp",
            Message.wa_message_id == wa_message_id,
            Message.owner_id == current_owner_id(),
        )
    )


def recent_from(
    session: Session,
    contact: Contact,
    limit: int = 20,
    include_deleted: bool = True,
) -> list[Message]:
    """Most recent messages from one contact, newest last."""

    query = (
        select(Message)
        .where(Message.contact_id == contact.id)
        .where(Message.owner_id == current_owner_id())
        .order_by(Message.sent_at.desc())
        .limit(limit)
    )

    messages = list(session.scalars(query))

    if not include_deleted:
        messages = [m for m in messages if not m.is_deleted]

    return list(reversed(messages))


def list_deleted(session: Session, limit: int = 50) -> list[Message]:
    """Every message that was deleted, newest first."""

    query = (
        select(Message)
        .where(Message.is_deleted.is_(True))
        .where(Message.owner_id == current_owner_id())
        .order_by(Message.deleted_at.desc())
        .limit(limit)
    )

    return list(session.scalars(query))


def all_contacts(session: Session) -> list[Contact]:
    return list(
        session.scalars(
            select(Contact)
            .where(Contact.owner_id == current_owner_id())
            .order_by(Contact.push_name)
        )
    )


def resolve_contact(session: Session, query: str) -> Contact | None:
    """Find a contact by name, phone number, JID or part of a name.

    Used by the Telegram commands, where the owner types a name
    rather than an id.
    """

    if not query:
        return None

    text = query.strip().lower()
    owner_id = current_owner_id()

    contact = session.scalar(
        select(Contact).where(
            Contact.owner_id == owner_id,
            or_(
                Contact.jid == query,
                Contact.phone == query,
                Contact.push_name == query,
            ),
        )
    )

    if contact is not None:
        return contact

    # Phone numbers are often written without a country code.
    digits = "".join(ch for ch in text if ch.isdigit())

    if digits:

        contacts = list(
            session.scalars(select(Contact).where(Contact.owner_id == owner_id))
        )

        for candidate in contacts:

            candidate_digits = "".join(
                ch for ch in (candidate.phone or "") if ch.isdigit()
            )

            if candidate_digits and (
                candidate_digits.endswith(digits) or digits.endswith(candidate_digits)
            ):
                return candidate

    # Partial name match.
    partial = session.scalar(
        select(Contact).where(
            Contact.owner_id == owner_id,
            Contact.push_name.isnot(None),
            Contact.push_name.ilike(f"%{query}%"),
        )
    )

    if partial is not None:
        return partial

    contacts = list(
        session.scalars(select(Contact).where(Contact.owner_id == owner_id))
    )

    for candidate in contacts:

        name = (candidate.push_name or "").lower()

        if name and (name.startswith(text) or text.startswith(name)):
            return candidate

    return None


# =====================================================
# PRIVACY MODES
# =====================================================

def get_preference(session: Session, contact: Contact) -> ContactPreference:
    """Preference row for a contact, created on demand."""

    preference = session.scalar(
        select(ContactPreference).where(
            ContactPreference.contact_id == contact.id
        )
    )

    if preference is None:

        preference = ContactPreference(
            contact_id=contact.id,
            notify_mode=DEFAULT_NOTIFY_MODE,
        )

        session.add(preference)
        session.flush()

    return preference


def set_notify_mode(session: Session, contact: Contact, mode: str) -> bool:
    """Change how much the owner hears about this contact."""

    preference = get_preference(session, contact)

    changed = preference.set_mode(mode)

    if changed:
        session.flush()

    return changed


# =====================================================
# SUMMARIES AND SEARCH
# =====================================================

def needs_summary(session: Session, limit: int = 20) -> list[Message]:
    """Messages that have content but no summary yet."""

    query = (
        select(Message)
        .where(Message.owner_id == current_owner_id())
        .where(Message.summary.is_(None))
        .where(Message.body != "")
        .order_by(Message.sent_at.desc())
        .limit(limit)
    )

    return list(session.scalars(query))


def set_summary(session: Session, message: Message, summary: str) -> None:
    message.summary = summary
    session.flush()


def set_embedding(session: Session, message: Message, vector: list[float]) -> None:
    message.embedding = list(vector)
    session.flush()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def semantic_search(
    session: Session,
    query_vector: list[float],
    limit: int = 10,
    contact_id: int | None = None,
) -> list[tuple[Message, float]]:
    """Messages most similar to a query vector, best first."""

    query = select(Message).where(
        Message.embedding.isnot(None),
        Message.owner_id == current_owner_id(),
    )

    if contact_id is not None:
        query = query.where(Message.contact_id == contact_id)

    results = []

    for message in session.scalars(query):

        score = _cosine(query_vector, message.embedding or [])

        if score > 0:
            results.append((message, score))

    results.sort(key=lambda pair: pair[1], reverse=True)

    return results[:limit]


def keyword_search(
    session: Session,
    text: str,
    limit: int = 10,
    contact_id: int | None = None,
) -> list[Message]:
    """Plain text search, used when no embedding is available."""

    if not text:
        return []

    query = (
        select(Message)
        .where(Message.body.ilike(f"%{text}%"))
        .where(Message.owner_id == current_owner_id())
        .order_by(Message.sent_at.desc())
        .limit(limit)
    )

    if contact_id is not None:
        query = query.where(Message.contact_id == contact_id)

    return list(session.scalars(query))
