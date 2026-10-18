"""`GET /v1/stats/weekly`: per-ISO-week totals computed in SQL, zero-filled.

`GET /v1/stats/summary`: totals, totals per sport type and the longest activity for a range.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.api.activities import ACTIVITY_EXAMPLE, ActivityOut
from trainsync.api.deps import ClockDep, SessionmakerDep, require_api_key
from trainsync.api.errors import UNAUTHORIZED, error
from trainsync.core.clock import Clock
from trainsync.db.repositories.reads import ActivityFilter, ReadRepository, Totals, week_start

router = APIRouter(prefix="/v1/stats", tags=["stats"], dependencies=[Depends(require_api_key)])

DEFAULT_WEEKS = 12
MAX_WEEKS = 520

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


@router.get(
    "/weekly",
    summary="Weekly totals",
    description=(
        "Count, distance, moving time and elevation per ISO week (Monday start, UTC) for "
        "activities whose start date falls in `from`..`to` (both inclusive). Weeks without "
        "activities are returned with zeros. Defaults to the last 12 weeks. Soft-deleted "
        "activities are excluded."
    ),
    response_model=WeeklyStats,
    response_model_by_alias=True,
    responses={
        **UNAUTHORIZED,
        400: error("`to` before `from`, or over 520 weeks", "`to` is before `from`"),
    },
)
async def weekly(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-09-30"])] = None,
    sport_type: Annotated[str | None, Query(examples=["Run"])] = None,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
) -> WeeklyStats:
    start, end = _resolve_range(start, end, clock)
    first_week, last_week = week_start(start), week_start(end)
    if (last_week - first_week).days // 7 + 1 > MAX_WEEKS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"at most {MAX_WEEKS} weeks")

    async with sessionmaker() as session:
        reads = ReadRepository(session)
        athlete_ids = await reads.active_athlete_ids(athlete_id)
        activity_filter = _range_filter(athlete_ids, start, end, sport_type)
        weeks = await reads.weekly_stats(activity_filter, first_week, last_week)
        last_synced_at = await reads.last_synced_at(athlete_ids)
    return WeeklyStats.model_validate(
        {
            "from": start,
            "to": end,
            "sport_type": sport_type,
            "weeks": [
                Week(
                    week_start=w.week_start,
                    count=w.count,
                    distance_m=w.distance_m,
                    moving_time_s=w.moving_time_s,
                    elevation_gain_m=w.elevation_gain_m,
                )
                for w in weeks
            ],
            "last_synced_at": last_synced_at,
        }
    )


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


class StatsSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
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
            ]
        },
        populate_by_name=True,
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


@router.get(
    "/summary",
    summary="Totals for a date range",
    description=(
        "Count, distance, moving time and elevation for activities whose start date falls in "
        "`from`..`to` (both inclusive, UTC days), the same totals per sport type (sorted by "
        "sport type), and the longest activity: the one with the greatest distance, the newest "
        "on a tie. An empty range gives zeros, an empty `by_sport` and a null `longest`. "
        "Defaults to the last 12 weeks. Soft-deleted activities are excluded."
    ),
    response_model=StatsSummary,
    response_model_by_alias=True,
    responses={**UNAUTHORIZED, 400: error("`to` before `from`", "`to` is before `from`")},
)
async def summary(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-09-30"])] = None,
    sport_type: Annotated[str | None, Query(examples=["Run"])] = None,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
) -> StatsSummary:
    start, end = _resolve_range(start, end, clock)
    async with sessionmaker() as session:
        reads = ReadRepository(session)
        athlete_ids = await reads.active_athlete_ids(athlete_id)
        result = await reads.summary(_range_filter(athlete_ids, start, end, sport_type))
        last_synced_at = await reads.last_synced_at(athlete_ids)
    return StatsSummary.model_validate(
        {
            "from": start,
            "to": end,
            "sport_type": sport_type,
            "totals": TotalsOut.from_totals(result.totals),
            "by_sport": [
                SportTotalsOut(
                    sport_type=s.sport_type,
                    count=s.count,
                    distance_m=s.distance_m,
                    moving_time_s=s.moving_time_s,
                    elevation_gain_m=s.elevation_gain_m,
                )
                for s in result.by_sport
            ],
            "longest": None
            if result.longest is None
            else ActivityOut.from_row(result.longest, include_raw=False),
            "last_synced_at": last_synced_at,
        }
    )


def _resolve_range(start: date | None, end: date | None, clock: Clock) -> tuple[date, date]:
    """Defaults (`to` today in UTC, `from` 12 ISO weeks back) and the `to` ≥ `from` check."""
    end = end or clock().astimezone(UTC).date()
    start = start or week_start(end) - timedelta(weeks=DEFAULT_WEEKS - 1)
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
    return start, end


def _range_filter(
    athlete_ids: list[int], start: date, end: date, sport_type: str | None
) -> ActivityFilter:
    """Inclusive UTC days `start`..`end` as a half-open timestamp range."""
    return ActivityFilter(
        athlete_ids, _utc_midnight(start), _utc_midnight(end + timedelta(days=1)), sport_type
    )


def _utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
