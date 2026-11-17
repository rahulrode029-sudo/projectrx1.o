"""Password login for the web UI.

The site holds private WhatsApp messages, so every page except the
health check and this login flow requires a session. Visitors get a
limited number of password attempts per IP to stop brute forcing.
"""

import secrets
import threading
import time
from datetime import timedelta
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from config import settings

bp = Blueprint("auth", __name__)

SESSION_KEY = "rx_logged_in"
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300

# Failed logins per IP: {ip: (attempts, lock_until)}
_failures: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()

# Pages that must stay reachable without logging in.
PUBLIC_PATHS = ("/health", "/login")


def _client_ip() -> str:
    """The visitor's IP, honouring nginx's forwarded header."""

    forwarded = request.headers.get("X-Forwarded-For", "")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.remote_addr or "unknown"


def _too_many_attempts(ip: str) -> bool:
    with _lock:
        attempts, lock_until = _failures.get(ip, (0, 0.0))

        if lock_until and time.time() < lock_until:
            return True

        if lock_until and time.time() >= lock_until:
            _failures.pop(ip, None)

        return False


def _failed_attempt(ip: str) -> None:
    with _lock:
        attempts, lock_until = _failures.get(ip, (0, 0.0))
        attempts += 1

        if attempts >= MAX_ATTEMPTS:
            lock_until = time.time() + LOCK_SECONDS

        _failures[ip] = (attempts, lock_until)


def _clear_attempts(ip: str) -> None:
    with _lock:
        _failures.pop(ip, None)


def is_logged_in() -> bool:
    return bool(session.get(SESSION_KEY))


def login_required(view):
    """Redirect anonymous visitors to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

        return view(*args, **kwargs)

    return wrapped


def configure(app) -> None:
    """Wire login settings and the global guard into the Flask app."""

    app.secret_key = settings.flask_secret_key or secrets.token_hex(32)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.before_request
    def _require_login():
        path = request.path

        if path == "/static" or path.startswith("/static/"):
            return None

        if path in PUBLIC_PATHS or path.startswith("/wa/"):
            # /wa/* uses its own X-WA-Secret header: the sidecar is a
            # server, not a browser with a session cookie.
            return None

        if not is_logged_in():
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

        return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Show the password form and check submissions."""

    next_url = request.values.get("next") or "/"

    # Never redirect a visitor to another site after logging in.
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    ip = _client_ip()

    if request.method == "GET":
        if is_logged_in():
            return redirect(next_url)

        return render_template("login.html", next_url=next_url, error=None)

    if _too_many_attempts(ip):
        return render_template(
            "login.html",
            next_url=next_url,
            error="Too many attempts. Try again in five minutes.",
        ), 429

    password = request.form.get("password", "")

    if not settings.web_password or not secrets.compare_digest(
        password, settings.web_password
    ):
        _failed_attempt(ip)

        return render_template(
            "login.html", next_url=next_url, error="Wrong password."
        ), 401

    _clear_attempts(ip)
    session.clear()
    session[SESSION_KEY] = True
    session.permanent = True

    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True})

    return redirect(next_url)


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    """End the session."""

    session.clear()

    return redirect(url_for("auth.login"))
