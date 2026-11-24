"""Observed WhatsApp active sessions for one contact.

A session is the window between a contact becoming available on
WhatsApp and going away again. The sidecar observes the presence
events; this table stores the result under the same owner as the
contact, so one account can never read another account's sessions.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class PresenceSession(Base):
    """One `started -> ended` WhatsApp-active window."""

    __tablename__ = "presence_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_users.id"), nullable=True, index=True
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id"), index=True
    )

    # Stored as naive UTC, like the rest of the archive. The web layer
    # converts to the owner's display time zone when rendering.
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    contact = relationship("Contact")

    __table_args__ = (
        UniqueConstraint(
            "owner_id", "contact_id", "started_at",
            name="ux_presence_owner_contact_start",
        ),
        Index("ix_presence_contact_start", "contact_id", "started_at"),
    )
