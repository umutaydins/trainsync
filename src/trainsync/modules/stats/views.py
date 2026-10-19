"""The `/v1/stats` views: resolve the period, apply the user's settings, use the cache (P8.10)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.settings import Settings
from trainsync.modules.activities.reads import ActivityFilter, ReadRepository
from trainsync.modules.activities.router import ActivityOut
from trainsync.modules.auth.service import Principal
from trainsync.modules.stats import body, consistency, food, strength
from trainsync.modules.stats import series as series_data
from trainsync.modules.stats.cache import StatsCache
from trainsync.modules.stats.endurance import SportGroup
from trainsync.modules.stats.periods import (
    Bucket,
    Period,
    Resolved,
    default_bucket,
    local_today,
    resolve,
)
from trainsync.modules.stats.schemas import (
    HeatmapDayOut,
    HeatmapOut,
    PointOut,
    PrOut,
    PrsOut,
    SeriesOut,
    WindowOut,
)
from trainsync.modules.stats.scope import Scope
from trainsync.modules.stats.series import Metric
from trainsync.modules.stats.service import StatsContext, first_day, progress
from trainsync.modules.stats.totals import SportTotalsOut, StatsSummary, TotalsOut
from trainsync.modules.users.settings import effective_for


@dataclass(frozen=True, slots=True)
class Request:
    principal: Principal
    now: datetime
    settings: Settings
    redis: Redis


@dataclass(frozen=True, slots=True)
class Choice:
    period: Period
    start: date | None = None
    end: date | None = None


async def summary_of(
    session: AsyncSession,
    principal: Principal,
    now: datetime,
    settings: Settings,
    redis: Redis,
    period: Period,
) -> StatsSummary:
    """The summary as the API would answer it, for the worker's digests (P8.11)."""
    request = Request(principal, now, settings, redis)
    return await summary(session, request, Choice(period), None, None)


def zone_of(principal: Principal) -> ZoneInfo:
    return ZoneInfo(principal.timezone)


async def _context(
    session: AsyncSession, request: Request, athlete_id: int | None = None
) -> StatsContext:
    principal = request.principal
    athletes = await ReadRepository(session, principal.user_id).active_athlete_ids(athlete_id)
    chosen = await effective_for(session, request.settings, principal.user_id, principal.timezone)
    zone = zone_of(principal)
    return StatsContext(
        session=session,
        scope=Scope(principal.user_id, zone, athletes),
        today=local_today(request.now, zone),
        sugar_limit_g=chosen.sugar_limit_g,
        e1rm_max_reps=request.settings.stats_e1rm_max_reps,
    )


async def _resolve(ctx: StatsContext, choice: Choice) -> tuple[Resolved, date | None]:
    first = await first_day(ctx.session, ctx.scope)
    try:
        resolved = resolve(
            choice.period, ctx.today, start=choice.start, end=choice.end, first_day=first
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return resolved, first


async def _cached[M: BaseModel](
    ctx: StatsContext,
    request: Request,
    view: str,
    params: dict[str, object],
    model: type[M],
    build: Callable[[], Awaitable[M]],
    window_days: int,
) -> M:
    cache = StatsCache(request.redis, request.settings)
    if not cache.worth_it(window_days):
        return await build()

    async def compute() -> str:
        return (await build()).model_dump_json(by_alias=True)

    scope = ctx.scope
    keyed = {**params, "today": ctx.today, "tz": scope.zone.key, "athletes": scope.athlete_ids}
    raw = await cache.get_or_compute(ctx.session, ctx.scope.user_id, view, keyed, compute)
    return model.model_validate_json(raw)


async def summary(
    session: AsyncSession,
    request: Request,
    choice: Choice,
    sport_type: str | None,
    athlete_id: int | None,
) -> StatsSummary:
    ctx = await _context(session, request, athlete_id)
    resolved, first = await _resolve(ctx, choice)

    async def build() -> StatsSummary:
        reads = ReadRepository(session, ctx.scope.user_id)
        lower, upper = resolved.window.bounds(ctx.scope.zone)
        athletes = ctx.scope.athlete_ids
        totals = await reads.summary(ActivityFilter(athletes, lower, upper, sport_type))
        blocks = await progress(ctx, resolved, first)
        return StatsSummary.model_validate(
            {
                **blocks.model_dump(by_alias=True),
                "from": resolved.window.start,
                "to": resolved.window.end,
                "sport_type": sport_type,
                "totals": TotalsOut.from_totals(totals.totals),
                "by_sport": [
                    SportTotalsOut.model_validate(s, from_attributes=True) for s in totals.by_sport
                ],
                "longest": None
                if totals.longest is None
                else ActivityOut.from_row(totals.longest, include_raw=False),
                "last_synced_at": await reads.last_synced_at(athletes),
            }
        )

    params: dict[str, object] = {
        "period": resolved.period,
        "window": resolved.window,
        "sport_type": sport_type,
        "sugar": ctx.sugar_limit_g,
    }
    return await _cached(ctx, request, "summary", params, StatsSummary, build, resolved.window.days)


async def series(
    session: AsyncSession,
    request: Request,
    choice: Choice,
    metric: Metric,
    bucket: Bucket | None,
    sport: SportGroup | None,
) -> SeriesOut:
    ctx = await _context(session, request)
    resolved, _ = await _resolve(ctx, choice)
    window = resolved.window
    chosen = bucket or default_bucket(window)

    async def build() -> SeriesOut:
        values = await series_data.daily(session, ctx.scope, window, metric, sport)
        points = series_data.bucketize(values, window, chosen, mean=metric is Metric.WEIGHT)
        averages: dict[date, float] = {}
        if metric is Metric.WEIGHT and chosen is Bucket.DAY:
            lead_in = window.start - timedelta(body.MOVING_AVERAGE_DAYS - 1)
            logged = await body.weights(session, ctx.scope, lead_in, window.end)
            averages = {d: a for d, a in body.moving_averages(logged).items() if d in window}
        target = None
        if metric is Metric.KCAL:
            target = await food.kcal_target(session, ctx.scope.user_id)
        return SeriesOut(
            metric=metric,
            period=resolved.period,
            bucket=chosen,
            timezone=ctx.scope.zone.key,
            window=WindowOut.of(window),
            sport=sport if metric in series_data.SPORT_METRICS else None,
            target=None if target is None else float(target),
            points=[
                PointOut(start=p.start, value=p.value, moving_average=averages.get(p.start))
                for p in points
            ],
        )

    params: dict[str, object] = {
        "metric": metric,
        "period": resolved.period,
        "window": window,
        "bucket": chosen,
        "sport": sport,
    }
    return await _cached(ctx, request, "series", params, SeriesOut, build, window.days)


async def heatmap(session: AsyncSession, request: Request, year: int | None) -> HeatmapOut:
    ctx = await _context(session, request)
    window = consistency.heatmap_window(year, ctx.today)

    async def build() -> HeatmapOut:
        days = await consistency.heatmap(session, ctx.scope, window)
        return HeatmapOut(
            year=window.end.year,
            rolling=year is None,
            window=WindowOut.of(window),
            timezone=ctx.scope.zone.key,
            max_value=max((d.minutes for d in days), default=0.0),
            days=[
                HeatmapDayOut(day=d.day, value=d.minutes, sessions=d.sessions, checkin=d.checkin)
                for d in days
            ],
        )

    return await _cached(ctx, request, "heatmap", {"year": year}, HeatmapOut, build, window.days)


async def prs(
    session: AsyncSession, request: Request, choice: Choice, exercise_id: int | None
) -> PrsOut:
    ctx = await _context(session, request)
    resolved, _ = await _resolve(ctx, choice)
    events = await strength.pr_events(
        session, ctx.scope, ctx.e1rm_max_reps, resolved.window, exercise_id
    )
    return PrsOut(
        period=resolved.period,
        window=WindowOut.of(resolved.window),
        count=len(events),
        records=[
            PrOut(
                exercise_id=e.exercise_id,
                name=e.name,
                workout_id=e.workout_id,
                achieved_at=e.achieved_at,
                e1rm_kg=float(e.e1rm_kg),
                previous_kg=None if e.previous_kg is None else float(e.previous_kg),
            )
            for e in reversed(events)
        ],
    )
