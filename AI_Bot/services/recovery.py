"""Forgot-password delivery and one-time reset links.

No password is ever sent or recovered. A verified phone number gets a
short code, and after that a single-use link to choose a new password.
Messages go through the user's linked WhatsApp first; if that sidecar
is offline, MSG91 SMS is used instead.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from config import settings
from database.database import session_scope
from models import OtpCode, ResetToken, WebUser
from services.passwords import hash_password, verify_password

OTP_MINUTES = 10
RESET_MINUTES = 15
MAX_OTP_ATTEMPTS = 5
HELPER_TIMEOUT = 5.0
SMS_TIMEOUT = 10.0


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# =====================================================
# OTP
# =====================================================

def create_otp(user: WebUser) -> str:
    """Issue a fresh six-digit code, invalidating earlier ones."""

    code = f"{secrets.randbelow(1_000_000):06d}"

    with session_scope() as session:
        session.query(OtpCode).filter(
            OtpCode.user_id == user.id, OtpCode.used.is_(False)
        ).update({OtpCode.used: True}, synchronize_session=False)

        session.add(
            OtpCode(
                user_id=user.id,
                phone=user.phone,
                code_hash=hash_password(code),
                expires_at=_now() + timedelta(minutes=OTP_MINUTES),
            )
        )
        session.commit()

    return code


def _latest_otp(user_id: int) -> OtpCode | None:
    with session_scope() as session:
        return session.scalar(
            select(OtpCode)
            .where(OtpCode.user_id == user_id, OtpCode.used.is_(False))
            .order_by(OtpCode.created_at.desc(), OtpCode.id.desc())
        )


def verify_otp(user: WebUser, code: str) -> tuple[bool, str]:
    """Check a code. Returns (ok, reason)."""

    record = _latest_otp(user.id)

    if record is None:
        return False, "Request a code first."

    if record.expires_at < _now():
        return False, "That code expired. Request a new one."

    if record.attempts >= MAX_OTP_ATTEMPTS:
        return False, "Too many wrong attempts. Request a new code."

    if not verify_password((code or "").strip(), record.code_hash):
        with session_scope() as session:
            row = session.get(OtpCode, record.id)
            row.attempts += 1
            session.commit()

        return False, "Wrong code."

    with session_scope() as session:
        row = session.get(OtpCode, record.id)
        row.used = True
        session.commit()

    return True, ""


def otp_attempts_blocked(user: WebUser) -> bool:
    """True when the newest code has been tried too many times."""

    record = _latest_otp(user.id)

    return record is not None and record.attempts >= MAX_OTP_ATTEMPTS


# =====================================================
# RESET TOKENS
# =====================================================

def create_reset_link(user: WebUser) -> str:
    """Create a single-use link and return it."""

    token = secrets.token_urlsafe(32)
    base = settings.public_base_url.rstrip("/")

    with session_scope() as session:
        session.query(ResetToken).filter(
            ResetToken.user_id == user.id, ResetToken.used_at.is_(None)
        ).update(
            {ResetToken.used_at: _now()}, synchronize_session=False
        )

        session.add(
            ResetToken(
                user_id=user.id,
                token_hash=_token_hash(token),
                expires_at=_now() + timedelta(minutes=RESET_MINUTES),
            )
        )
        session.commit()

    return f"{base}/reset-password?token={token}"


def reset_user_for_token(token: str) -> WebUser | None:
    """Return the account for a valid, unused link, else None."""

    if not token:
        return None

    with session_scope() as session:
        row = session.scalar(
            select(ResetToken).where(
                ResetToken.token_hash == _token_hash(token),
                ResetToken.used_at.is_(None),
            )
        )

        if row is None or row.expires_at < _now():
            return None

        return session.get(WebUser, row.user_id)


def consume_token_for_user(user_id: int) -> None:
    """Invalidate every unused link once a password has been set."""

    with session_scope() as session:
        session.query(ResetToken).filter(
            ResetToken.user_id == user_id, ResetToken.used_at.is_(None)
        ).update({ResetToken.used_at: _now()}, synchronize_session=False)
        session.commit()


# =====================================================
# DELIVERY
# =====================================================

def _send_whatsapp(user: WebUser, text: str) -> bool:
    """Ask the user's sidecar to message their own WhatsApp number."""

    if not user.wa_token or not user.wa_port:
        return False

    url = f"http://127.0.0.1:{user.wa_port}/send"
    jid = f"{user.phone}@s.whatsapp.net"

    try:
        response = httpx.post(
            url,
            json={"to": jid, "text": text},
            headers={"X-RX-Token": user.wa_token},
            timeout=HELPER_TIMEOUT,
        )
        return response.status_code < 400
    except httpx.HTTPError as error:
        print(f"WhatsApp OTP delivery failed for {user.username}: {error}")
        return False


def _send_sms(user: WebUser, text: str, template_id: str, value: str) -> bool:
    """Send through MSG91. Variables in the template must be var1/var2."""

    if not (
        settings.msg91_auth_key
        and settings.msg91_sender_id
        and template_id
        and user.phone
    ):
        return False

    payload = {
        "authkey": settings.msg91_auth_key,
        "template_id": template_id,
        "mobile": user.phone,
        "sender": settings.msg91_sender_id,
        "var1": value,
        "var2": user.username,
    }

    try:
        response = httpx.post(
            settings.msg91_api_url, json=payload, timeout=SMS_TIMEOUT
        )
        return response.status_code < 400
    except httpx.HTTPError as error:
        print(f"MSG91 delivery failed for {user.username}: {error}")
        return False


def send_otp(user: WebUser, code: str) -> str | None:
    """Deliver a code. Returns 'whatsapp', 'sms', or None."""

    text = f"Your RX login code is {code}. It expires in {OTP_MINUTES} minutes."

    if _send_whatsapp(user, text):
        return "whatsapp"

    if _send_sms(user, text, settings.msg91_otp_template_id, code):
        return "sms"

    return None


def send_reset_link(user: WebUser, link: str) -> str | None:
    """Deliver the reset link. Returns the channel used, or None."""

    text = (
        f"Hi {user.username}, your RX username is {user.username}.\n"
        f"Set a new password here: {link}\n"
        f"This link expires in {RESET_MINUTES} minutes."
    )

    if _send_whatsapp(user, text):
        return "whatsapp"

    if _send_sms(user, text, settings.msg91_reset_template_id, link):
        return "sms"

    return None
