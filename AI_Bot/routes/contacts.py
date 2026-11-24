"""Add and remove WhatsApp contacts from the web UI."""

from flask import Blueprint, flash, redirect, request, url_for
from sqlalchemy import select

from database.database import session_scope
from models import Alert, Contact, Conversation, Message, PresenceSession
from services import memory, presence
from services.tenancy import current_owner_id

bp = Blueprint("contacts", __name__, url_prefix="/contacts")


def _jid_from_form(phone, jid):
    """Turn a phone number or JID from the form into a contact JID."""

    raw = (jid or "").strip()

    if raw and "@" in raw:
        return raw

    if not raw:
        raw = phone or ""

    digits = "".join(character for character in raw if character.isdigit())

    if not digits:
        return None

    return f"{digits}@s.whatsapp.net"


@bp.route("/add", methods=["POST"])
def add():
    """Create a contact so it can be filtered before its first message."""

    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    jid_input = (request.form.get("jid") or "").strip()

    jid = _jid_from_form(phone, jid_input)

    if not jid:
        flash("Enter a phone number or a WhatsApp JID.", "error")
        return redirect(url_for("messages_page"))

    with session_scope() as session:
        existing = session.scalar(
            select(Contact).where(
                Contact.jid == jid, Contact.owner_id == current_owner_id()
            )
        )

        if existing is not None:
            flash("That contact is already in the list.", "error")
            return redirect(url_for("messages_page"))

        digits = "".join(character for character in phone if character.isdigit())

        contact = memory.get_or_create_contact(
            session,
            jid,
            push_name=name or None,
            phone=digits or None,
        )

        session.commit()
        label = contact.label

    flash(f"Added {label}.", "success")
    return redirect(url_for("messages_page", contact=label))


@bp.route("/<int:contact_id>/delete", methods=["POST"])
def delete(contact_id: int):
    """Remove a contact and everything stored under it."""

    with session_scope() as session:
        contact = session.get(Contact, contact_id)

        if contact is None or contact.owner_id != current_owner_id():
            flash("That contact no longer exists.", "error")
            return redirect(url_for("messages_page"))

        label = contact.label

        # Foreign keys are enforced, so the rows that point at the
        # contact must go first. Messages and alerts belong to the
        # archive being removed; conversations are kept but detached.
        session.query(Alert).filter(Alert.contact_id == contact.id).delete(
            synchronize_session=False
        )
        session.query(Message).filter(Message.contact_id == contact.id).delete(
            synchronize_session=False
        )
        session.query(PresenceSession).filter(
            PresenceSession.contact_id == contact.id
        ).delete(synchronize_session=False)
        session.query(Conversation).filter(
            Conversation.contact_id == contact.id
        ).update({Conversation.contact_id: None}, synchronize_session=False)

        session.delete(contact)  # preference cascades
        session.commit()

    flash(f"Removed {label} and its stored messages.", "success")
    return redirect(url_for("messages_page"))


@bp.route("/<int:contact_id>/tracking", methods=["POST"])
def tracking(contact_id: int):
    """Opt this contact in or out of WhatsApp session tracking."""

    enabled = request.form.get("enabled", "").lower() in (
        "1", "true", "yes", "on"
    )

    label = presence.set_tracking(contact_id, enabled)

    if label is None:
        flash("That contact no longer exists.", "error")
    else:
        state = "on" if enabled else "off"
        flash(f"WhatsApp session tracking for {label} is now {state}.", "success")

    next_url = request.form.get("next", "")

    # Only follow local paths. A posted `next` value must never become
    # an open redirect to another site.
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("messages_page")

    return redirect(next_url)
