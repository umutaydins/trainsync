"""Accounts, sessions, invites and password resets. Secrets are stored only as SHA-256 hashes."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, check_in, utc_timestamp


class UserRole(StrEnum):
    OWNER = "owner"
    USER = "user"


class User(Base):
    """`email` is stored trimmed and lower-cased. `password_hash` is argon2id; an owner created
    by the migration has an unusable one until `scripts/owner.py set-password`."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(check_in("role", UserRole), name="role"),
        # Exactly one owner.
        Index("uq_users_owner", "role", unique=True, postgresql_where=text("role = 'owner'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(8), server_default=text("'user'"))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)
    deleted_at: Mapped[datetime | None] = utc_timestamp(nullable=True)


class AuthSession(Base):
    """A signed-in device. The token is shown once; `expires_at` slides on use up to
    `created_at + SESSION_MAX_AGE_DAYS`."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)
    last_seen_at: Mapped[datetime] = utc_timestamp(default_now=True)
    expires_at: Mapped[datetime] = utc_timestamp()
    revoked_at: Mapped[datetime | None] = utc_timestamp(nullable=True)


class Invite(Base):
    """A single-use registration code created by the owner."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)
    expires_at: Mapped[datetime] = utc_timestamp()
    used_at: Mapped[datetime | None] = utc_timestamp(nullable=True)
    used_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = utc_timestamp(nullable=True)


class PasswordReset(Base):
    """A one-time reset link the owner generated for a user (no email yet, ADR 0034)."""

    __tablename__ = "password_resets"
    __table_args__ = (Index("ix_password_resets_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)
    expires_at: Mapped[datetime] = utc_timestamp()
    used_at: Mapped[datetime | None] = utc_timestamp(nullable=True)
