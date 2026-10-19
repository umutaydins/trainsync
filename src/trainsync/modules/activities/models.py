"""Synced Strava activities."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, utc_timestamp


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
    start_date: Mapped[datetime] = utc_timestamp()
    distance_m: Mapped[float] = mapped_column(Float)
    moving_time_s: Mapped[int] = mapped_column(Integer)
    elapsed_time_s: Mapped[int] = mapped_column(Integer)
    elevation_gain_m: Mapped[float] = mapped_column(Float)
    average_heartrate: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any]]
    deleted_at: Mapped[datetime | None] = utc_timestamp(nullable=True)
    synced_at: Mapped[datetime] = utc_timestamp(default_now=True)
