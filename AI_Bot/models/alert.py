"""Web notifications.

Alerts are written here and shown on the Messages page. `seen` lets
the page highlight what has arrived since the owner last looked.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class Alert(Base):
    """One notification shown on the website."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_users.id"), nullable=True, index=True
    )

    # message: a new message arrived
    # summary: a one-line AI summary of a new message
    # deleted: a contact deleted a message
    kind: Mapped[str] = mapped_column(String(16), index=True)

    title: Mapped[str] = mapped_column(String(256), default="")
    body: Mapped[str] = mapped_column(Text, default="")

    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )
    wa_message_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )

    seen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, index=True, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_alerts_seen_created", "seen", "created_at"),
    )
