"""Sync runs (resumable backfill, incremental) and webhook events."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, check_in, owner_id, utc_timestamp


class SyncKind(StrEnum):
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"


class SyncStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WebhookStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(check_in("kind", SyncKind), name="kind"),
        CheckConstraint(check_in("status", SyncStatus), name="status"),
        Index("ix_sync_runs_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = owner_id()
    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    cursor: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    pages: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    upserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = utc_timestamp(default_now=True)
    # Heartbeat, bumped with every checkpoint: tells a live run from one whose worker died.
    updated_at: Mapped[datetime] = utc_timestamp(default_now=True)
    finished_at: Mapped[datetime | None] = utc_timestamp(nullable=True)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint(check_in("status", WebhookStatus), name="status"),
        Index("ix_webhook_events_status_received_at", "status", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any]]
    status: Mapped[str] = mapped_column(String(16), server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    received_at: Mapped[datetime] = utc_timestamp(default_now=True)
    # Set on every claim; drives the retry backoff and the stuck-in-processing check.
    last_attempt_at: Mapped[datetime | None] = utc_timestamp(nullable=True)
    processed_at: Mapped[datetime | None] = utc_timestamp(nullable=True)
