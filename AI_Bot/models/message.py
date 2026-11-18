"""Stored messages.

`wa_message_id` is the important column: it is the platform's own id
for the message, and it is the key a WhatsApp REVOKE event carries.
Matching on it is how a deleted message is found and flagged, because
the revoke event itself contains no content.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    UniqueConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class Message(Base):
    """One message, captured the moment it arrives."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_users.id"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), index=True, default="whatsapp")
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )

    # Platform message id. Unique per channel, so a revoke event can
    # be matched back to exactly one stored row.
    wa_message_id: Mapped[str] = mapped_column(String(128), index=True)

    from_me: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_jid: Mapped[str | None] = mapped_column(String(96), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    media_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    sent_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Delete tracking. `is_deleted` is set when a revoke event arrives.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delete_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # AI helpers: a one-line summary and the embedding used for
    # semantic search.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(JSON, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
    contact = relationship("Contact")

    __table_args__ = (
        UniqueConstraint(
            "owner_id", "channel", "wa_message_id", name="ux_messages_owner_wamid"
        ),
        Index("ix_messages_contact_sent", "contact_id", "sent_at"),
    )

    @property
    def preview(self) -> str:
        """Short text for listings."""

        text = (self.body or "").strip()

        if not text and self.media_type:
            return f"[{self.media_type}]"

        return text[:200]
