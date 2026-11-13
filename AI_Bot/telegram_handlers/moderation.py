"""Moderation for the Telegram side.

Keeps track of who is allowed to talk to the bot and blocks the
obvious abuse without touching the message archive.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database.database import session_scope
from models import User
from services import spam_detector

# A user who trips the spam check this many times gets muted.
STRIKES_TO_MUTE = 3

# How long a muted user stays muted.
MUTE_MINUTES = 60


def is_blocked(user_id: int) -> bool:
    """Whether a Telegram user is currently muted."""

    with session_scope() as session:

        user = session.scalar(
            select(User).where(
                User.platform == "telegram",
                User.platform_id == str(user_id),
            )
        )

        if user is None:
            return False

        muted_until = getattr(user, "muted_until", None)

        if muted_until is None:
            return False

        if muted_until.tzinfo is None:
            muted_until = muted_until.replace(tzinfo=timezone.utc)

        return muted_until > datetime.now(timezone.utc)


def record_message(user_id: int, text: str) -> bool:
    """Record a message and apply a strike if it looks like spam.

    Returns True when the user should be muted.
    """

    verdict = spam_detector.check_text(text)

    if not verdict.is_spam:
        return False

    with session_scope() as session:

        user = session.scalar(
            select(User).where(
                User.platform == "telegram",
                User.platform_id == str(user_id),
            )
        )

        if user is None:

            user = User(
                platform="telegram",
                platform_id=str(user_id),
            )
            session.add(user)
            session.flush()

        user.spam_strikes = (user.spam_strikes or 0) + 1

        should_mute = user.spam_strikes >= STRIKES_TO_MUTE

        if should_mute:
            user.muted_until = datetime.now(timezone.utc) + timedelta(
                minutes=MUTE_MINUTES
            )
            user.spam_strikes = 0

        session.commit()

    return should_mute
