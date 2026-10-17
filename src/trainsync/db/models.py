"""SQLAlchemy models for every table in docs/architecture.md → Data model."""

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


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


def _check_in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def _utc_timestamp(*, nullable: bool = False, default_now: bool = False) -> Any:
    return mapped_column(
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if default_now else None,
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB}


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strava_athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True
    )
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = _utc_timestamp()
    scope: Mapped[str] = mapped_column(Text)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_athlete_start_date", "athlete_id", text("start_date DESC")),
        Index("ix_activities_athlete_sport_start_date", "athlete_id", "sport_type", "start_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strava_activity_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    sport_type: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[datetime] = _utc_timestamp()
    distance_m: Mapped[float] = mapped_column(Float)
    moving_time_s: Mapped[int] = mapped_column(Integer)
    elapsed_time_s: Mapped[int] = mapped_column(Integer)
    elevation_gain_m: Mapped[float] = mapped_column(Float)
    average_heartrate: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any]]
    deleted_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)
    synced_at: Mapped[datetime] = _utc_timestamp(default_now=True)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(_check_in("kind", SyncKind), name="kind"),
        CheckConstraint(_check_in("status", SyncStatus), name="status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    cursor: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    pages: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    upserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    # Heartbeat, bumped with every checkpoint: tells a live run from one whose worker died.
    updated_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    finished_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint(_check_in("status", WebhookStatus), name="status"),
        Index("ix_webhook_events_status_received_at", "status", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any]]
    status: Mapped[str] = mapped_column(String(16), server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    received_at: Mapped[datetime] = _utc_timestamp(default_now=True)
    # Set on every claim; drives the retry backoff and the stuck-in-processing check.
    last_attempt_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)
    processed_at: Mapped[datetime | None] = _utc_timestamp(nullable=True)
