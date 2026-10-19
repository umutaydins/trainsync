"""Per-user settings (ADR 0036). The account itself (`users`) belongs to `modules.auth`."""

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, utc_timestamp


class UserSettings(Base):
    """One row per user. A null column means "the environment default" (`BOT_TONE`,
    `CHECKIN_TIME`, …), so a changed default reaches every user who never chose."""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("tone IN ('neutral', 'hardcore')", name="tone"),
        CheckConstraint("intensity IN ('normal', 'savage')", name="intensity"),
        CheckConstraint("profanity IN ('roast', 'max')", name="profanity"),
        CheckConstraint("lang IN ('en', 'tr')", name="lang"),
        CheckConstraint("checkin_reminder_minutes BETWEEN 0 AND 720", name="reminder"),
        CheckConstraint("sugar_limit_g > 0 AND sugar_limit_g <= 1000", name="sugar_limit"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tone: Mapped[str | None] = mapped_column(String(8))
    intensity: Mapped[str | None] = mapped_column(String(8))
    profanity: Mapped[str | None] = mapped_column(String(8))
    lang: Mapped[str | None] = mapped_column(String(2))
    checkin_enabled: Mapped[bool | None] = mapped_column(Boolean)
    # Weekly and monthly progress digests (P8.11).
    stats_digest_enabled: Mapped[bool | None] = mapped_column(Boolean)
    checkin_time: Mapped[time | None] = mapped_column(Time)
    checkin_reminder_minutes: Mapped[int | None] = mapped_column(Integer)
    quiet_hours: Mapped[str | None] = mapped_column(String(11))
    workout_reminder_time: Mapped[time | None] = mapped_column(Time)
    sugar_limit_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    # ISO 3166-1 alpha-2; picks the emergency number of the distress reply.
    country: Mapped[str | None] = mapped_column(String(2))
    updated_at: Mapped[datetime] = utc_timestamp(default_now=True)
