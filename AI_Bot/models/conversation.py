"""Chat threads. One row per WhatsApp conversation (1:1 chat or group)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class Conversation(Base):
    """A chat the owner takes part in."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_users.id"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), index=True, default="whatsapp")
    chat_jid: Mapped[str] = mapped_column(String(96), index=True)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    contact = relationship("Contact")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )
