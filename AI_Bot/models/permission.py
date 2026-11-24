"""Per-contact settings.

`notify_mode` controls what the owner is told about a contact's
messages without opening them:

  summary  - a one-line summary is sent, the raw text is not
  full     - the raw text is sent
  silent   - nothing is sent, the owner asks for it later
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


NOTIFY_MODES = ("summary", "full", "silent")

DEFAULT_NOTIFY_MODE = "summary"


class ContactPreference(Base):
    """What the bot should do with one contact's messages."""

    __tablename__ = "contact_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id"), unique=True, index=True
    )

    notify_mode: Mapped[str] = mapped_column(
        String(16), default=DEFAULT_NOTIFY_MODE
    )
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_deleted: Mapped[bool] = mapped_column(Boolean, default=True)
    # Opt in to observing this contact's WhatsApp active sessions.
    # Off by default: presence is only watched for contacts the owner
    # explicitly chooses, which keeps sidecar subscriptions bounded.
    track_sessions: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    contact = relationship("Contact", back_populates="preference")

    def set_mode(self, mode: str) -> bool:
        """Change the notify mode. Returns False for an unknown mode."""

        if mode not in NOTIFY_MODES:
            return False

        self.notify_mode = mode

        return True
