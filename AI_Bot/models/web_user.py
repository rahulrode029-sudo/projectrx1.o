"""Web accounts, OTP codes and password reset tokens.

Every row in the archive points at one of these accounts through
`owner_id`, which is what keeps users from seeing each other's data.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class WebUser(Base):
    """A person who can sign in to the website."""

    __tablename__ = "web_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Used by the forgot-password flow. Stored with the country code.
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # "admin" can manage accounts. Everyone else is "user".
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # The sidecar sends this token with every event so the app knows
    # which account the event belongs to. It is an API key, not a
    # login password, so it has to be readable by the server.
    wa_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    wa_port: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)

    # Bumped on password change so old sessions stop working.
    session_version: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("username", name="ux_web_users_username"),
        UniqueConstraint("phone", name="ux_web_users_phone"),
    )

    @property
    def label(self) -> str:
        return self.display_name or self.username


class OtpCode(Base):
    """A short-lived phone verification code for a password reset."""

    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("web_users.id"), nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ResetToken(Base):
    """A single-use link that lets a user choose a new password."""

    __tablename__ = "reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("web_users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_reset_tokens_user", "user_id"),)
