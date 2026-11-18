"""Account login for the web UI.

Every page except the health check and the account-recovery flow needs
a session. The signed-in account is also the tenant: the request sets
its id once and every archive query uses it.
"""

import threading
import time
from datetime import timedelta
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from services import accounts
from services.passwords import verify_password
from services.tenancy import clear_owner, set_owner

bp = Blueprint("auth", __name__)

SESSION_KEY = "rx_logged_in"
USER_ID_KEY = "rx_user_id"
VERSION_KEY = "rx_session_version"
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300

# Failed logins per IP: {ip: (attempts, lock_until)}
_failures: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()

# Pages reachable without signing in. Recovery links are public by
# design: the token in the URL is the credential.
PUBLIC_PATHS = (
    "/health",
    "/login",
    "/forgot-password",
    "/forgot-password/send",
    "/forgot-password/verify",
    "/reset-password",
)


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


def current_user():
    """The signed-in account, or None if the session is no longer valid."""

    if not is_logged_in():
        return None

    if hasattr(g, "rx_user"):
        return g.rx_user

    user = accounts.get_user(session.get(USER_ID_KEY, 0))

    if (
        user is None
        or not user.is_active
        or user.session_version != session.get(VERSION_KEY)
    ):
        session.clear()
        g.rx_user = None
        return None

    g.rx_user = user
    return user


def login_required(view):
    """Redirect anonymous visitors to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    """Only let account administrators through."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()

        if user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

        if user.role != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


def configure(app) -> None:
    """Wire login settings, the auth guard and the tenant context."""

    from config import settings

    app.secret_key = settings.flask_secret_key or "rx-insecure-development-key"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.before_request
    def _require_login():
        path = request.path

        # Never let a worker thread carry the previous request's tenant.
        clear_owner()

        if path == "/static" or path.startswith("/static/"):
            return None

        if path in PUBLIC_PATHS or path.startswith("/wa/"):
            return None

        user = current_user()

        if user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

        # One place sets the tenant for the whole request. If this is
        # missing, memory queries raise instead of using someone else's
        # account as a default.
        set_owner(user.id)

        return None

    @app.context_processor
    def _inject_current_user():
        return {"viewer": current_user()}


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Show the username + password form and check submissions."""

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

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password", "")

    user = accounts.authenticate(username, password)

    if user is None:
        _failed_attempt(ip)

        return render_template(
            "login.html",
            next_url=next_url,
            username=username,
            error="Wrong username or password.",
        ), 401

    _clear_attempts(ip)
    session.clear()
    session[SESSION_KEY] = True
    session[USER_ID_KEY] = user.id
    session[VERSION_KEY] = user.session_version
    session.permanent = True

    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True})

    return redirect(next_url)


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    """End the session."""

    session.clear()

    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET"])
def account_page():
    """Profile and security settings for the signed-in user."""

    user = current_user()

    return render_template("account.html", user=user)


@bp.route("/account/profile", methods=["POST"])
def account_profile():
    """Update the display name and the recovery phone number."""

    user = current_user()
    display_name = (request.form.get("display_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    if not phone:
        flash("A phone number is required for password recovery.", "error")
    else:
        error = accounts.set_phone(user.id, phone)

        if error:
            flash(error, "error")
        else:
            accounts.set_display_name(user.id, display_name)
            flash("Profile updated.", "success")

    return redirect(url_for("auth.account_page"))


@bp.route("/account/password", methods=["POST"])
def account_password():
    """Change your own password and invalidate older sessions."""

    user = current_user()
    old = request.form.get("old_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not verify_password(old, user.password_hash):
        flash("Your current password is wrong.", "error")
    elif len(new) < 8:
        flash("The new password must be at least 8 characters.", "error")
    elif new != confirm:
        flash("The two new passwords do not match.", "error")
    elif accounts.set_password(user.id, new):
        updated = accounts.get_user(user.id)
        session[VERSION_KEY] = updated.session_version
        flash("Password changed.", "success")
    else:
        flash("Could not change the password.", "error")

    return redirect(url_for("auth.account_page"))
