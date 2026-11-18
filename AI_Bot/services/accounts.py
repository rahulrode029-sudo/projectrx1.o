"""Web accounts and the isolation rules around them."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database.database import session_scope
from models import Alert, Contact, Conversation, Message, WebUser
from services.passwords import hash_password, verify_password

_bootstrap_admin_id: int | None = None

# Helper servers start here; each account gets the next free port.
HELPER_PORT_BASE = 8787

USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,32}$")


def normalize_phone(value: str | None) -> str:
    """Keep digits only and add India's country code when it is missing."""

    if not value:
        return ""

    digits = re.sub(r"\D", "", str(value))

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 10:
        digits = "91" + digits

    return digits


def _next_port(session: Session) -> int:
    ports = [int(port) for port in session.scalars(select(WebUser.wa_port)) if port]

    return max(max(ports, default=HELPER_PORT_BASE - 1) + 1, HELPER_PORT_BASE)


def _assign_legacy_rows(session: Session, admin_id: int) -> None:
    """Anything captured before accounts existed belongs to the admin."""

    for model in (Contact, Conversation, Message, Alert):
        session.query(model).filter(model.owner_id.is_(None)).update(
            {model.owner_id: admin_id}, synchronize_session=False
        )

    session.commit()


def bootstrap_admin() -> int:
    """Create the first admin if needed and return its id."""

    global _bootstrap_admin_id

    with session_scope() as session:
        admin = session.scalar(select(WebUser).where(WebUser.role == "admin"))

        if admin is None:
            username = (settings.admin_username or "admin").strip().lower()
            password = settings.admin_password or settings.web_password

            if not USERNAME_PATTERN.match(username):
                username = "admin"

            if not password:
                raise RuntimeError(
                    "Set ADMIN_PASSWORD (or WEB_PASSWORD) before starting RX."
                )

            admin = WebUser(
                username=username,
                password_hash=hash_password(password),
                display_name="Admin",
                phone=normalize_phone(settings.admin_phone),
                role="admin",
                is_active=True,
                wa_token=secrets.token_urlsafe(24),
            )
            session.add(admin)
            session.flush()
            admin.wa_port = _next_port(session)
            session.commit()

        _bootstrap_admin_id = admin.id
        admin_id = admin.id

    _assign_legacy_rows_standalone(admin_id)

    return admin_id


def _assign_legacy_rows_standalone(admin_id: int) -> None:
    with session_scope() as session:
        _assign_legacy_rows(session, admin_id)


def bootstrap_admin_id() -> int:
    """The admin id, used as the default tenant in scripts and tests."""

    if _bootstrap_admin_id is None:
        return bootstrap_admin()

    return _bootstrap_admin_id


def reset_bootstrap_cache() -> None:
    """Forget the cached id (used when a test database is replaced)."""

    global _bootstrap_admin_id
    _bootstrap_admin_id = None


def find_by_username(username: str) -> WebUser | None:
    with session_scope() as session:
        return session.scalar(
            select(WebUser).where(
                WebUser.username == (username or "").strip().lower()
            )
        )


def find_by_phone(phone: str) -> WebUser | None:
    number = normalize_phone(phone)

    if not number:
        return None

    with session_scope() as session:
        return session.scalar(select(WebUser).where(WebUser.phone == number))


def find_by_wa_token(token: str) -> WebUser | None:
    if not token:
        return None

    with session_scope() as session:
        return session.scalar(select(WebUser).where(WebUser.wa_token == token))


def get_user(user_id: int) -> WebUser | None:
    with session_scope() as session:
        return session.get(WebUser, int(user_id))


def authenticate(username: str, password: str) -> WebUser | None:
    user = find_by_username(username)

    if user is None or not user.is_active:
        return None

    if not verify_password(password or "", user.password_hash):
        return None

    return user


def validate_new_account(username, password, phone) -> tuple[str, str] | None:
    """Return an error message, or None when the details are usable."""

    name = (username or "").strip().lower()

    if not USERNAME_PATTERN.match(name):
        return "Username must be 3-32 characters: letters, numbers, dot, dash or underscore."

    if len(password or "") < 8:
        return "Password must be at least 8 characters."

    number = normalize_phone(phone)

    if len(number) < 10:
        return "Enter a valid phone number."

    if find_by_username(name) is not None:
        return "That username is already taken."

    if find_by_phone(number) is not None:
        return "That phone number is already in use."

    return None


def create_user(
    username: str,
    password: str,
    display_name: str = "",
    phone: str = "",
    role: str = "user",
) -> WebUser:
    """Create one web account with its own WhatsApp helper port."""

    error = validate_new_account(username, password, phone)

    if error:
        raise ValueError(error)

    with session_scope() as session:
        user = WebUser(
            username=username.strip().lower(),
            password_hash=hash_password(password),
            display_name=(display_name or "").strip() or None,
            phone=normalize_phone(phone),
            role="user" if role != "admin" else "admin",
            is_active=True,
            wa_token=secrets.token_urlsafe(24),
        )
        session.add(user)
        session.flush()
        user.wa_port = _next_port(session)
        session.commit()

        return user


def active_users() -> list[WebUser]:
    """Accounts whose sidecars should be running."""

    with session_scope() as session:
        return list(
            session.scalars(
                select(WebUser).where(WebUser.is_active.is_(True)).order_by(WebUser.id)
            )
        )


def all_users() -> list[WebUser]:
    with session_scope() as session:
        return list(session.scalars(select(WebUser).order_by(WebUser.id)))


def set_active(user_id: int, active: bool) -> bool:
    with session_scope() as session:
        user = session.get(WebUser, user_id)

        if user is None:
            return False

        user.is_active = bool(active)
        user.session_version += 1
        session.commit()

        return True


def set_password(user_id: int, password: str) -> bool:
    if len(password or "") < 8:
        return False

    with session_scope() as session:
        user = session.get(WebUser, user_id)

        if user is None:
            return False

        user.password_hash = hash_password(password)
        user.session_version += 1
        session.commit()

        return True


def set_display_name(user_id: int, display_name: str) -> None:
    with session_scope() as session:
        user = session.get(WebUser, user_id)

        if user is not None:
            user.display_name = (display_name or "").strip() or None
            session.commit()


def set_phone(user_id: int, phone: str) -> str | None:
    """Return an error message, or None on success."""

    number = normalize_phone(phone)

    if len(number) < 10:
        return "Enter a valid phone number."

    with session_scope() as session:
        clash = session.scalar(
            select(WebUser).where(WebUser.phone == number, WebUser.id != user_id)
        )

        if clash is not None:
            return "That phone number is already in use."

        user = session.get(WebUser, user_id)

        if user is None:
            return "No such account."

        user.phone = number
        session.commit()

    return None


def delete_user(user_id: int) -> str | None:
    """Remove an account and every archive row it owns.

    Returns the deleted account's sidecar token so the supervisor can
    stop its process. The last admin may not be deleted.
    """

    from models import OtpCode, ResetToken

    with session_scope() as session:
        user = session.get(WebUser, user_id)

        if user is None:
            return None

        if user.role == "admin":
            other_admins = len(
                list(
                    session.scalars(
                        select(WebUser).where(
                            WebUser.role == "admin", WebUser.id != user_id
                        )
                    )
                )
            )

            if other_admins == 0:
                return None

        token = user.wa_token

        # Archive rows use owner_id; recovery rows use user_id.
        for model in (Alert, Message, Conversation, Contact):
            session.query(model).filter(model.owner_id == user_id).delete(
                synchronize_session=False
            )

        for model in (OtpCode, ResetToken):
            session.query(model).filter(model.user_id == user_id).delete(
                synchronize_session=False
            )

        session.delete(user)
        session.commit()

        return token
