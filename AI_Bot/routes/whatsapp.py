"""HTTP endpoints for the WhatsApp sidecar.

The sidecar is the only thing that talks to WhatsApp. It sends raw
events here and this module decides what to store and what to tell
the owner about.
"""

import asyncio

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from config import settings
from database.database import session_scope
from models import Contact, Message
from services import memory
from services import whatsapp as whatsapp_service

bp = Blueprint("whatsapp", __name__, url_prefix="/wa")


def _authorised() -> bool:
    """Check the shared secret the sidecar sends.

    Intake is refused outright when no secret is configured, so the
    endpoint can never be left open by accident.
    """

    secret = settings.wa_shared_secret

    if not secret:
        print(
            "WA_SHARED_SECRET is not set in .env, refusing WhatsApp "
            "events. Set it and restart."
        )
        return False

    return request.headers.get("X-WA-Secret", "") == secret


def _handle_contact(payload):
    """Record contact details the sidecar learned about."""

    jid = payload.get("jid")

    if not jid:
        return {"ok": False, "reason": "missing jid"}

    with session_scope() as session:

        memory.get_or_create_contact(
            session,
            jid,
            push_name=payload.get("push_name"),
            phone=payload.get("phone"),
        )

        session.commit()

    return {"ok": True}


def _handle_bulk_delete(payload):
    """A 'delete for me' or bulk delete: flag every listed message."""

    keys = payload.get("keys") or []

    flagged = 0

    for key in keys:

        wa_message_id = key.get("id") if isinstance(key, dict) else key

        if not wa_message_id:
            continue

        with session_scope() as session:

            message = memory.mark_deleted(session, wa_message_id, "delete")

            session.commit()

            if message is not None:
                flagged += 1

    return {"ok": True, "flagged": flagged}


@bp.route("/events", methods=["POST"])
def events():
    """Receive one event from the sidecar."""

    if not _authorised():
        return jsonify({"error": "unauthorised"}), 401

    payload = request.get_json(silent=True) or {}

    kind = payload.get("type")

    try:

        if kind == "message":
            result = asyncio.run(
                whatsapp_service.process_message_event(payload)
            )

        elif kind == "revoke":
            result = asyncio.run(
                whatsapp_service.process_revoke_event(payload)
            )

        elif kind == "delete":
            result = _handle_bulk_delete(payload)

        elif kind == "contact":
            result = _handle_contact(payload)

        else:
            return jsonify({"error": f"unknown event type '{kind}'"}), 400

    except Exception as error:

        print(f"WhatsApp event failed: {error}")

        return jsonify({"error": str(error)}), 500

    return jsonify(result)


@bp.route("/messages", methods=["GET"])
def messages():
    """Query stored messages."""

    if not _authorised():
        return jsonify({"error": "unauthorised"}), 401

    contact_query = request.args.get("contact")

    limit = min(int(request.args.get("limit", 50)), 500)

    show_deleted = request.args.get("deleted", "").lower() in ("1", "true", "yes")

    with session_scope() as session:

        if show_deleted:

            rows = memory.list_deleted(session, limit=limit)

        elif contact_query:

            contact = memory.resolve_contact(session, contact_query)

            if contact is None:
                return jsonify({"error": f"no contact '{contact_query}'"}), 404

            rows = memory.recent_from(session, contact, limit=limit)

        else:

            rows = list(
                session.scalars(
                    select(Message)
                    .order_by(Message.sent_at.desc())
                    .limit(limit)
                )
            )

        payload = [
            {
                "wa_message_id": row.wa_message_id,
                "contact": row.contact.label if row.contact else None,
                "body": row.body,
                "summary": row.summary,
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "is_deleted": row.is_deleted,
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            }
            for row in rows
        ]

    return jsonify({"count": len(payload), "messages": payload})


@bp.route("/contacts", methods=["GET"])
def contacts():
    """List everyone who has written to the owner."""

    if not _authorised():
        return jsonify({"error": "unauthorised"}), 401

    with session_scope() as session:

        rows = memory.all_contacts(session)

        payload = [
            {
                "jid": row.jid,
                "name": row.label,
                "phone": row.phone,
                "notify_mode": memory.get_preference(session, row).notify_mode,
            }
            for row in rows
        ]

    return jsonify({"count": len(payload), "contacts": payload})


@bp.route("/mode", methods=["POST"])
def set_mode():
    """Change how much the owner hears about a contact."""

    if not _authorised():
        return jsonify({"error": "unauthorised"}), 401

    payload = request.get_json(silent=True) or {}

    contact_query = payload.get("contact")

    mode = payload.get("mode")

    if not contact_query or not mode:
        return jsonify({"error": "contact and mode are required"}), 400

    with session_scope() as session:

        contact = memory.resolve_contact(session, contact_query)

        if contact is None:
            return jsonify({"error": f"no contact '{contact_query}'"}), 404

        changed = memory.set_notify_mode(session, contact, mode)

        session.commit()

        label = contact.label

    if not changed:
        return jsonify({"error": f"unknown mode '{mode}'"}), 400

    return jsonify({"ok": True, "contact": label, "mode": mode})
