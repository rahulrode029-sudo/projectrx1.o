"""The people involved: the owner of the system, and their contacts."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class User(Base):
    """A person who talks to the bot (a Telegram user)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), default="telegram")

    # The platform's own id for this user, for example a Telegram
    # chat id. Stored as text because ids differ per platform.
    platform_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)

    # Moderation state.
    spam_strikes: Mapped[int] = mapped_column(Integer, default=0)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Contact(Base):
    """Someone who writes to the owner on WhatsApp.

    `jid` is WhatsApp's internal id for the contact, for example
    `919876543210@s.whatsapp.net`. It is the stable key across
    reconnects, unlike a phone number.
    """

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The web account this contact belongs to. Two users may know the
    # same person, so the JID is unique per owner, not globally.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_users.id"), nullable=True, index=True
    )

    platform: Mapped[str] = mapped_column(String(20), default="whatsapp")
    jid: Mapped[str] = mapped_column(String(96), index=True)
    push_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    preference = relationship(
        "ContactPreference",
        back_populates="contact",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "jid", name="ux_contacts_owner_jid"),
    )

    @property
    def label(self) -> str:
        """Best human-readable name for this contact."""

        return self.push_name or self.phone or self.jid
