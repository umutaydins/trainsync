"""Daily check-ins (P6.9, ADR 0020)."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, check_in, owner_id, utc_timestamp


class CheckinStatus(StrEnum):
    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    REST = "rest"
    SICK_OR_INJURED = "sick_or_injured"


class DailyCheckin(Base):
    """The evening report of one local day (P6.9, ADR 0020): did the owner train, and how it
    went. One row per date; `PUT /v1/checkins/{date}` upserts it."""

    __tablename__ = "daily_checkins"
    __table_args__ = (
        CheckConstraint(check_in("status", CheckinStatus), name="status"),
        CheckConstraint("sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 24", name="sleep_hours"),
        CheckConstraint("energy_1_5 IS NULL OR energy_1_5 BETWEEN 1 AND 5", name="energy_1_5"),
        CheckConstraint(
            "body_weight_kg IS NULL OR (body_weight_kg > 0 AND body_weight_kg < 500)",
            name="body_weight_kg",
        ),
        UniqueConstraint("user_id", "date", name="uq_daily_checkins_user_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = owner_id()
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    workout_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workouts.id", ondelete="SET NULL")
    )
    reason_note: Mapped[str | None] = mapped_column(Text)
    sleep_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    energy_1_5: Mapped[int | None] = mapped_column(Integer)
    body_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)
    updated_at: Mapped[datetime] = utc_timestamp(default_now=True)
