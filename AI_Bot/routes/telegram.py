"""Telegram related HTTP endpoints.

Useful for checking the bot is wired up correctly, and for pushing a
message to the owner from the web UI or a script.
"""

import asyncio

from flask import Blueprint, jsonify, request

from database.database import session_scope
from models import User
from services import whatsapp as whatsapp_service

bp = Blueprint("telegram", __name__, url_prefix="/telegram")


@bp.route("/status", methods=["GET"])
def status():
    """Whether the bot can reach the owner."""

    with session_scope() as session:

        owner = session.query(User).filter_by(is_owner=True).first()

        chat_id = owner.platform_id if owner else None

        name = owner.display_name if owner else None

    return jsonify(
        {
            "ok": True,
            "token_set": bool(whatsapp_service.settings.has_telegram),
            "owner_known": bool(chat_id),
            "owner_name": name,
        }
    )


@bp.route("/send", methods=["POST"])
def send():
    """Send a message to the owner on Telegram."""

    payload = request.get_json(silent=True) or {}

    text = (payload.get("text") or "").strip()

    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        sent = asyncio.run(whatsapp_service.notify_owner(text))
    except Exception as error:

        print(f"Telegram send failed: {error}")

        return jsonify({"error": str(error)}), 500

    if not sent:
        return jsonify(
            {"error": "could not send, the owner chat id is unknown"}
        ), 503

    return jsonify({"ok": True})
