"""Central configuration for the AI Bot suite.

Every setting comes from the environment (loaded from .env), so no
secret ever lives in the source tree. Import `settings` from here
instead of reading os.getenv() in scattered modules.
"""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _enable_utf8_output():
    """Make the console speak UTF-8.

    Windows consoles still default to cp1252, which raises
    UnicodeEncodeError the moment a contact name contains an emoji
    or a non-Latin script. Errors are replaced rather than raised so
    a stray character can never take the bot down.
    """

    for stream in (sys.stdout, sys.stderr):

        reconfigure = getattr(stream, "reconfigure", None)

        if reconfigure is None:
            continue

        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_enable_utf8_output()


def _env(name, default=None, required=False):
    """Read an environment variable, optionally requiring it to be set."""

    value = os.getenv(name, default)

    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Add it to {BASE_DIR / '.env'}."
        )

    return value


def _env_bool(name, default=False):
    """Read a true/false environment variable."""

    value = (_env(name, "") or "").strip().lower()

    if not value:
        return default

    return value in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- AI ---
    gemini_api_key: str
    gemini_chat_model: str
    gemini_fallback_models: tuple[str, ...]
    gemini_live_model: str

    # --- Telegram ---
    telegram_bot_token: str
    telegram_owner_id: str

    # --- WhatsApp ---
    wa_shared_secret: str
    wa_owner_phone: str
    wa_pairing_phone: str
    wa_sidecar_url: str
    wa_helper_url: str

    # --- Movies ---
    tmdb_api_key: str
    watch_region: str

    # --- Web app ---
    web_password: str
    flask_secret_key: str
    web_host: str
    web_port: int
    web_debug: bool

    # --- Accounts and recovery ---
    admin_username: str
    admin_password: str
    admin_phone: str
    public_base_url: str
    msg91_api_url: str
    msg91_auth_key: str
    msg91_sender_id: str
    msg91_otp_template_id: str
    msg91_reset_template_id: str

    # --- Storage ---
    db_path: Path
    media_dir: Path

    @property
    def has_gemini(self):
        return bool(self.gemini_api_key)

    @property
    def has_telegram(self):
        return bool(self.telegram_bot_token)

    @property
    def has_tmdb(self):
        return bool(self.tmdb_api_key)


def _warn_about_malformed_env():
    """Catch a value that has another assignment glued onto it.

    This happens when a file has no trailing newline and something is
    appended to it. The result looks like a valid but wrong value, and
    the only symptom is an API rejecting it much later.
    """

    pattern = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*=")

    for name, value in os.environ.items():

        if not name.startswith(
            ("GEMINI", "TELEGRAM", "TMDB", "WA_", "DB_", "MEDIA_", "ADMIN_", "MSG91_")
        ):
            continue

        if not value:
            continue

        match = pattern.search(value)

        if match and match.start() > 0:
            print(
                f"WARNING: the {name} value in .env looks malformed. It "
                f"contains another assignment at position {match.start()}, "
                f"which usually means the file was missing a newline. "
                f"Check .env and put every setting on its own line."
            )


def load_settings() -> Settings:
    """Build the settings object from the current environment."""

    db_path = Path(_env("DB_PATH", str(BASE_DIR / "database" / "chatbote.db")))

    media_dir = Path(_env("MEDIA_DIR", str(BASE_DIR / "database" / "media")))

    return Settings(
        gemini_api_key=_env("Gemini_API_KEY", ""),
        gemini_chat_model=_env("GEMINI_CHAT_MODEL", "gemini-3.6-flash"),
        # Flash models are frequently overloaded (503). Try the next one
        # in line instead of failing the user's request.
        gemini_fallback_models=tuple(
            model.strip()
            for model in _env(
                "GEMINI_FALLBACK_MODELS",
                "gemini-3.5-flash-lite,gemini-3.1-flash-lite,"
                "gemini-3.6-flash,gemini-3.5-flash",
            ).split(",")
            if model.strip()
        ),
        gemini_live_model=_env(
            "GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview"
        ),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", ""),
        telegram_owner_id=_env("TELEGRAM_OWNER_ID", ""),
        wa_shared_secret=_env("WA_SHARED_SECRET", ""),
        wa_owner_phone=_env("WA_OWNER_PHONE", ""),
        # The number the sidecar links to. Digits only, with the
        # country code.
        wa_pairing_phone=_env("WA_PAIRING_PHONE", ""),
        # Where the sidecar sends its events to: the Flask app.
        wa_sidecar_url=_env("WA_SIDECAR_URL", "http://127.0.0.1:5000"),
        # Where the app reads the login QR from: the sidecar helper.
        wa_helper_url=_env("WA_HELPER_URL", "http://127.0.0.1:8787"),
        tmdb_api_key=_env("TMDB_API_KEY", ""),
        watch_region=_env("WATCH_REGION", "IN"),
        # Password for the public web UI. Refuse to serve the site with
        # an empty password so it can never be left open by accident.
        web_password=_env("WEB_PASSWORD", ""),
        flask_secret_key=_env("FLASK_SECRET_KEY", ""),
        web_host=_env("WEB_HOST", "127.0.0.1"),
        web_port=int(_env("WEB_PORT", "5000")),
        web_debug=_env_bool("WEB_DEBUG", False),
        # First admin account. WEB_PASSWORD is kept as a fallback so an
        # existing single-password install upgrades without a downtime.
        admin_username=_env("ADMIN_USERNAME", "admin"),
        admin_password=_env("ADMIN_PASSWORD", _env("WEB_PASSWORD", "")),
        admin_phone=_env("ADMIN_PHONE", ""),
        # Used when a password-reset link is sent as a text message.
        public_base_url=_env("PUBLIC_BASE_URL", "http://127.0.0.1:5000"),
        msg91_api_url=_env(
            "MSG91_API_URL", "https://control.msg91.com/api/v5/flow/"
        ),
        msg91_auth_key=_env("MSG91_AUTH_KEY", ""),
        msg91_sender_id=_env("MSG91_SENDER_ID", "RXINFO"),
        msg91_otp_template_id=_env("MSG91_OTP_TEMPLATE_ID", ""),
        msg91_reset_template_id=_env("MSG91_RESET_TEMPLATE_ID", ""),
        db_path=db_path,
        media_dir=media_dir,
    )


settings = load_settings()

_warn_about_malformed_env()

if not settings.web_password:
    print(
        "WARNING: WEB_PASSWORD is not set. The web UI will refuse to "
        "start until it is. Add it to .env and restart."
    )

if not settings.flask_secret_key:
    print(
        "WARNING: FLASK_SECRET_KEY is not set. Session cookies will "
        "not survive a restart. Add it to .env and restart."
    )
