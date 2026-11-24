"""The Flask application.

This process serves the web UI, proxies chat and voice calls to
Gemini, and receives WhatsApp events from the sidecar.

Run it as its own process:

    python app.py
"""

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request
from sqlalchemy import func, select

from config import settings
from database.database import init_db, session_scope
from models import Alert, Message
from routes import admin, alerts, auth, chat, contacts, qr, recovery, voice, whatsapp
from services import memory, presence
from services.tenancy import current_owner_id

app = Flask(__name__)

app.register_blueprint(auth.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(recovery.bp)
app.register_blueprint(alerts.bp)
app.register_blueprint(chat.bp)
app.register_blueprint(contacts.bp)
app.register_blueprint(voice.bp)
app.register_blueprint(whatsapp.bp)
app.register_blueprint(qr.bp)

# Every page except /health and /login requires a session. /wa/* keeps
# its own shared-secret check for the sidecar.
auth.configure(app)

# Create the tables on import, not only when run as a script, so the
# schema exists however the app is started.
init_db()


def _display_time(value) -> str:
    """Show a stored UTC timestamp in the owner's local time zone."""

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


@app.route("/")
def home():
    """The chat and voice page."""

    with session_scope() as session:
        rows = presence.recent_sessions(session)
        sessions = [presence.session_data(row) for row in rows]

    return render_template("index.html", sessions=sessions)


def _messages_context() -> dict:
    """Everything the Messages page shows, scoped to the signed-in user."""

    contact_query = request.args.get("contact", "").strip()

    limit = 50
    owner_id = current_owner_id()

    with session_scope() as session:

        contacts = memory.all_contacts(session)

        contact = None

        if contact_query:
            contact = memory.resolve_contact(session, contact_query)

        if contact is not None:
            rows = memory.recent_from(session, contact, limit=limit)

        else:
            rows = list(
                session.scalars(
                    select(Message)
                    .where(Message.owner_id == owner_id)
                    .order_by(Message.sent_at.desc())
                    .limit(limit)
                )
            )

        contact_rows = [
            {
                "id": item.id,
                "label": item.label,
                "mode": memory.get_preference(session, item).notify_mode,
                "track": memory.get_preference(session, item).track_sessions,
            }
            for item in contacts
        ]

        message_rows = [
            {
                "id": row.id,
                "contact": row.contact.label if row.contact else "unknown",
                "body": row.body,
                "summary": row.summary,
                "sent_at": _display_time(row.sent_at),
                "is_deleted": row.is_deleted,
            }
            for row in rows
        ]

        session_rows = presence.recent_sessions(
            session,
            contact_id=contact.id if contact is not None else None,
        )

        sessions_data = [presence.session_data(row) for row in session_rows]

        alert_rows = list(
            session.scalars(
                select(Alert)
                .where(Alert.owner_id == owner_id)
                .order_by(Alert.seen, Alert.created_at.desc())
                .limit(20)
            )
        )

        alerts_data = [
            {
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "body": item.body,
                "seen": item.seen,
                "time": _display_time(item.created_at),
            }
            for item in alert_rows
        ]

        unread = session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.owner_id == owner_id, Alert.seen.is_(False))
        )

    return {
        "contacts": contact_rows,
        "messages": message_rows,
        "sessions": sessions_data,
        "alerts": alerts_data,
        "unread": unread,
        "query": contact_query,
    }


@app.route("/messages")
def messages_page():
    """Browse the captured WhatsApp messages."""

    return render_template("messages.html", **_messages_context())


@app.route("/messages/live")
def messages_live():
    """JSON snapshot used by the page to pick up new events on its own."""

    return jsonify(_messages_context())


@app.route("/health")
def health():
    """A quick check that the service is up."""

    return jsonify(
        {
            "ok": True,
            "gemini": settings.has_gemini,
            "whatsapp_intake": bool(settings.wa_shared_secret),
        }
    )


if __name__ == "__main__":
    print(f"Database: {settings.db_path}")
    print(f"Timezone: {settings.display_timezone}")
    print(f"Web app:  http://{settings.web_host}:{settings.web_port}")

    if not settings.web_password:
        print("WEB_PASSWORD is not set - the site will refuse visitors.")

    app.run(
        host=settings.web_host,
        port=settings.web_port,
        debug=settings.web_debug,
    )
