"""Activity totals of the read API: the weekly view and the classic summary fields (P2, P8.10).

`StatsSummary` keeps the fields `/v1/stats/summary` always had and adds the progress blocks.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.activities.reads import Totals
from trainsync.modules.activities.router import ACTIVITY_EXAMPLE, ActivityOut
from trainsync.modules.stats.examples import PROGRESS_EXAMPLE
from trainsync.modules.stats.schemas import ProgressOut

WEEK_EXAMPLE: dict[str, Any] = {
    "week_start": "2026-09-28",
    "count": 4,
    "distance_m": 42195.0,
    "moving_time_s": 14520,
    "elevation_gain_m": 310.5,
}


class Week(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [WEEK_EXAMPLE]})

    week_start: date = Field(description="Monday of the ISO week (UTC)")
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float


class WeeklyStats(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "from": "2026-09-28",
                    "to": "2026-10-11",
                    "sport_type": "Run",
                    "weeks": [WEEK_EXAMPLE, {**WEEK_EXAMPLE, "week_start": "2026-10-05"}],
                    "last_synced_at": "2026-10-18T09:30:02Z",
                }
            ]
        },
        populate_by_name=True,
    )

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    sport_type: str | None
    weeks: list[Week]
    last_synced_at: datetime | None


TOTALS_EXAMPLE: dict[str, Any] = {
    "count": 18,
    "distance_m": 352295.0,
    "moving_time_s": 74600,
    "elevation_gain_m": 2493.0,
}


class TotalsOut(BaseModel):
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float

    @classmethod
    def from_totals(cls, totals: Totals) -> "TotalsOut":
        return cls(
            count=totals.count,
            distance_m=totals.distance_m,
            moving_time_s=totals.moving_time_s,
            elevation_gain_m=totals.elevation_gain_m,
        )


class SportTotalsOut(BaseModel):
    sport_type: str
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float


SUMMARY_EXAMPLE: dict[str, Any] = {
    "from": "2026-09-07",
    "to": "2026-10-04",
    "sport_type": None,
    "totals": TOTALS_EXAMPLE,
    "by_sport": [
        {
            "sport_type": "Ride",
            "count": 4,
            "distance_m": 205000.0,
            "moving_time_s": 24600,
            "elevation_gain_m": 1850.0,
        },
        {
            "sport_type": "Run",
            "count": 11,
            "distance_m": 141295.0,
            "moving_time_s": 42300,
            "elevation_gain_m": 643.0,
        },
        {
            "sport_type": "Swim",
            "count": 3,
            "distance_m": 6000.0,
            "moving_time_s": 7700,
            "elevation_gain_m": 0.0,
        },
    ],
    "longest": ACTIVITY_EXAMPLE,
    "last_synced_at": "2026-10-18T09:30:02Z",
}


class ActivitySummary(BaseModel):
    """The activity fields of `/v1/stats/summary` (what the bot's /week reads)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [SUMMARY_EXAMPLE]}, populate_by_name=True
    )

    start: date = Field(alias="from")
    end: date = Field(alias="to")
    sport_type: str | None
    totals: TotalsOut
    by_sport: list[SportTotalsOut] = Field(description="The same totals per sport type, A to Z")
    longest: ActivityOut | None = Field(
        description="Greatest distance in the range (newest wins a tie); null if none"
    )
    last_synced_at: datetime | None


class StatsSummary(ActivitySummary, ProgressOut):
    """`/v1/stats/summary`: the activity fields and the progress blocks (ADR 0038)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{**SUMMARY_EXAMPLE, **PROGRESS_EXAMPLE}]},
        populate_by_name=True,
    )
