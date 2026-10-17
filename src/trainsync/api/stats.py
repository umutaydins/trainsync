"""`GET /v1/stats/weekly`: per-ISO-week totals computed in SQL, zero-filled."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.api.activities import UNAUTHORIZED
from trainsync.api.deps import ClockDep, SessionmakerDep, require_api_key
from trainsync.db.repositories.reads import ActivityFilter, ReadRepository, week_start

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
    responses={**UNAUTHORIZED, 400: {"description": "`to` before `from`, or over 520 weeks"}},
)
async def weekly(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-09-30"])] = None,
    sport_type: Annotated[str | None, Query(examples=["Run"])] = None,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
) -> WeeklyStats:
    end = end or clock().astimezone(UTC).date()
    start = start or week_start(end) - timedelta(weeks=DEFAULT_WEEKS - 1)
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
    first_week, last_week = week_start(start), week_start(end)
    if (last_week - first_week).days // 7 + 1 > MAX_WEEKS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"at most {MAX_WEEKS} weeks")

    async with sessionmaker() as session:
        reads = ReadRepository(session)
        athlete_ids = await reads.active_athlete_ids(athlete_id)
        activity_filter = ActivityFilter(
            athlete_ids, _utc_midnight(start), _utc_midnight(end + timedelta(days=1)), sport_type
        )
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


def _utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
