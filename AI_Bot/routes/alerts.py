"""Web actions for the notification panel."""

from flask import Blueprint, jsonify, redirect, request, url_for

from database.database import session_scope
from models import Alert

bp = Blueprint("alerts", __name__, url_prefix="/alerts")


@bp.route("/<int:alert_id>/seen", methods=["POST"])
def mark_seen(alert_id: int):
    """Mark one alert as seen."""

    with session_scope() as session:
        alert = session.get(Alert, alert_id)

        if alert is None:
            return jsonify({"error": "no such alert"}), 404

        alert.seen = True
        session.commit()

    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True})

    return redirect(url_for("messages_page"))


@bp.route("/seen-all", methods=["POST"])
def mark_all_seen():
    """Clear the unread highlight on every alert."""

    with session_scope() as session:
        for alert in session.query(Alert).filter(Alert.seen.is_(False)):
            alert.seen = True

        session.commit()

    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True})

    return redirect(url_for("messages_page"))
