"""`/v1/stats`: weekly totals, and the progress statistics of P8.10 (ADR 0038).

Every view is the signed-in user's, in their time zone. Windows of `STATS_CACHE_MIN_DAYS` or more
are cached, keyed by the user's data version.
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from trainsync.core.deps import ClockDep, RedisDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.activities.reads import ActivityFilter, ReadRepository, week_start
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.stats import views
from trainsync.modules.stats.endurance import SportGroup
from trainsync.modules.stats.periods import Bucket, Period, Window, local_today
from trainsync.modules.stats.schemas import HeatmapOut, PrsOut, SeriesOut
from trainsync.modules.stats.series import Metric
from trainsync.modules.stats.totals import StatsSummary, Week, WeeklyStats

router = APIRouter(prefix="/v1/stats", tags=["stats"])

DEFAULT_WEEKS = 12
MAX_WEEKS = 520
MAX_YEAR_OFFSET = 100
BAD_PERIOD = error("`to` before `from`, or `custom` without both", "`to` is before `from`")

StartQuery = Annotated[date | None, Query(alias="from", examples=["2026-09-01"])]
EndQuery = Annotated[date | None, Query(alias="to", examples=["2026-09-30"])]
PeriodQuery = Annotated[
    Period | None,
    Query(description="Omitted: `custom` when `from`/`to` are given, else the last 12 weeks"),
]


def default_range(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """`to` defaults to today, `from` to the Monday 12 ISO weeks back; `to` ≥ `from`."""
    end = end or today
    start = start or week_start(end) - timedelta(weeks=DEFAULT_WEEKS - 1)
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
    return start, end


@router.get(
    "/weekly",
    summary="Weekly totals",
    description=(
        "Count, distance, moving time and elevation per ISO week (Monday start, in your time "
        "zone) for activities whose start falls in `from`..`to` (local days, both inclusive). "
        "Weeks without activities are returned with zeros. Defaults to the last 12 weeks. "
        "Soft-deleted activities are excluded."
    ),
    response_model=WeeklyStats,
    response_model_by_alias=True,
    responses={
        **UNAUTHORIZED,
        400: error("`to` before `from`, or over 520 weeks", "`to` is before `from`"),
    },
)
async def weekly(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: StartQuery = None,
    end: EndQuery = None,
    sport_type: Annotated[str | None, Query(examples=["Run"])] = None,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
) -> WeeklyStats:
    zone = views.zone_of(principal)
    start, end = default_range(start, end, local_today(clock(), zone))
    first_week, last_week = week_start(start), week_start(end)
    if (last_week - first_week).days // 7 + 1 > MAX_WEEKS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"at most {MAX_WEEKS} weeks")
    lower, upper = Window(start, end).bounds(zone)
    async with sessionmaker() as session:
        reads = ReadRepository(session, principal.user_id)
        athlete_ids = await reads.active_athlete_ids(athlete_id)
        activity_filter = ActivityFilter(athlete_ids, lower, upper, sport_type)
        weeks = await reads.weekly_stats(activity_filter, first_week, last_week, zone.key)
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


@router.get(
    "/summary",
    summary="Progress for a period",
    description=(
        "Totals, totals per sport type and the longest activity (the fields this endpoint "
        "always had), and the progress blocks: endurance per sport group, strength, "
        "consistency, nutrition and body, each number with its change against the previous "
        "period of the same length (none for `all`). Periods are local days in your time zone "
        "(ADR 0038). An empty period gives zeros and null averages. Soft-deleted activities are "
        "excluded."
    ),
    response_model=StatsSummary,
    response_model_by_alias=True,
    responses={**UNAUTHORIZED, 400: BAD_PERIOD},
)
async def summary(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    settings: SettingsDep,
    redis: RedisDep,
    period: PeriodQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
    sport_type: Annotated[str | None, Query(examples=["Run"])] = None,
    athlete_id: Annotated[int | None, Query(description="Our athlete id")] = None,
) -> StatsSummary:
    request = views.Request(principal, clock(), settings, redis)
    if period is None:
        today = local_today(request.now, views.zone_of(principal))
        start, end = default_range(start, end, today)
        period = Period.CUSTOM
    async with sessionmaker() as session:
        return await views.summary(
            session, request, views.Choice(period, start, end), sport_type, athlete_id
        )


@router.get(
    "/series",
    summary="One metric over time",
    description=(
        "One point per bucket of the period: the sum of the bucket (zero-filled), or for "
        "`weight_kg` the mean (null without a weigh-in; with `bucket=day` also the 7-day moving "
        "average). `kcal` comes with the daily target. Default bucket: day up to 31 days, week "
        "up to 183 days, month beyond. `sport` limits the endurance metrics to a sport group."
    ),
    response_model=SeriesOut,
    response_model_by_alias=True,
    responses={**UNAUTHORIZED, 400: BAD_PERIOD},
)
async def series(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    settings: SettingsDep,
    redis: RedisDep,
    metric: Metric,
    period: Period = Period.MONTH,
    start: StartQuery = None,
    end: EndQuery = None,
    bucket: Bucket | None = None,
    sport: SportGroup | None = None,
) -> SeriesOut:
    request = views.Request(principal, clock(), settings, redis)
    async with sessionmaker() as session:
        return await views.series(
            session, request, views.Choice(period, start, end), metric, bucket, sport
        )


@router.get(
    "/heatmap",
    summary="Training calendar",
    description=(
        "One entry per local day: of `year` (1 January to 31 December, cut at today), or without "
        "`year` of the last 12 months up to today. Training minutes (activities' moving time "
        "plus workout durations), sessions and the check-in status; never a future day."
    ),
    response_model=HeatmapOut,
    responses={**UNAUTHORIZED, 400: error("Year out of range", "year out of range")},
)
async def heatmap(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    settings: SettingsDep,
    redis: RedisDep,
    year: Annotated[int | None, Query(examples=[2026])] = None,
) -> HeatmapOut:
    request = views.Request(principal, clock(), settings, redis)
    this_year = local_today(request.now, views.zone_of(principal)).year
    if year is not None and not 0 <= this_year - year <= MAX_YEAR_OFFSET:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "year out of range")
    async with sessionmaker() as session:
        return await views.heatmap(session, request, year)


@router.get(
    "/prs",
    summary="Personal records",
    description=(
        "Workouts that set a new e1RM record for a lift (Epley over working sets of at most "
        "`STATS_E1RM_MAX_REPS` reps, strictly above every earlier workout), newest first. "
        "Default period: `all`."
    ),
    response_model=PrsOut,
    response_model_by_alias=True,
    responses={**UNAUTHORIZED, 400: BAD_PERIOD},
)
async def prs(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    settings: SettingsDep,
    redis: RedisDep,
    period: Period = Period.ALL,
    start: StartQuery = None,
    end: EndQuery = None,
    exercise_id: int | None = None,
) -> PrsOut:
    request = views.Request(principal, clock(), settings, redis)
    async with sessionmaker() as session:
        return await views.prs(session, request, views.Choice(period, start, end), exercise_id)
