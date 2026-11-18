"""Database models for the bot suite.

Importing this package registers every table with the declarative
base, which is what `init_db()` relies on to create them.
"""

from models.alert import Alert
from models.conversation import Conversation
from models.message import Message
from models.permission import (
    DEFAULT_NOTIFY_MODE,
    NOTIFY_MODES,
    ContactPreference,
)
from models.user import Contact, User
from models.web_user import OtpCode, ResetToken, WebUser

__all__ = [
    "Alert",
    "Conversation",
    "Message",
    "ContactPreference",
    "NOTIFY_MODES",
    "DEFAULT_NOTIFY_MODE",
    "Contact",
    "User",
    "WebUser",
    "OtpCode",
    "ResetToken",
]
