"""Time series for the progress charts (P8.10, ADR 0038).

Each metric is summed (or, for body weight, averaged) per local day in Postgres; the days are
then folded into day / week / month buckets. Sum metrics are zero-filled; weight is None for a
bucket without a weigh-in.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.stats import body, consistency, food
from trainsync.modules.stats.endurance import SportGroup, activity_conditions, group_column
from trainsync.modules.stats.periods import Bucket, Window, bucket_start, bucket_starts
from trainsync.modules.stats.scope import Scope
from trainsync.modules.training.models import Workout, WorkoutSet


class Metric(StrEnum):
    DISTANCE = "distance_m"
    MOVING_TIME = "moving_time_s"
    ELEVATION = "elevation_gain_m"
    ACTIVITIES = "activities"
    SESSIONS = "sessions"
    SETS = "sets"
    REPS = "reps"
    TONNAGE = "tonnage_kg"
    KCAL = "kcal"
    PROTEIN = "protein_g"
    CARBS = "carbs_g"
    FAT = "fat_g"
    WEIGHT = "weight_kg"
    ACTIVE_MINUTES = "active_minutes"


ENDURANCE_METRICS = {
    Metric.DISTANCE: Activity.distance_m,
    Metric.MOVING_TIME: Activity.moving_time_s,
    Metric.ELEVATION: Activity.elevation_gain_m,
}
SET_METRICS: dict[Metric, Callable[[], ColumnElement[Any]]] = {
    Metric.SETS: func.count,
    Metric.REPS: lambda: func.sum(WorkoutSet.reps),
    Metric.TONNAGE: lambda: func.sum(WorkoutSet.reps * WorkoutSet.weight_kg),
}
FOOD_METRICS = {
    Metric.KCAL: "kcal",
    Metric.PROTEIN: "protein_g",
    Metric.CARBS: "carbs_g",
    Metric.FAT: "fat_g",
}
# Metrics of a single sport group when `sport` is given; the others ignore it.
SPORT_METRICS = frozenset({*ENDURANCE_METRICS, Metric.ACTIVITIES})

Daily = dict[date, float]


@dataclass(frozen=True, slots=True)
class Point:
    start: date
    value: float | None


async def _rows(session: AsyncSession, stmt: Any) -> Daily:
    return {day: float(value or 0) for day, value in (await session.execute(stmt)).all()}


async def _endurance(
    session: AsyncSession, scope: Scope, window: Window, metric: Metric, sport: SportGroup | None
) -> Daily:
    day = scope.local_date(Activity.start_date)
    value = func.count() if metric is Metric.ACTIVITIES else func.sum(ENDURANCE_METRICS[metric])
    conditions = activity_conditions(scope, window)
    if sport is not None:
        conditions.append(group_column() == sport.value)
    return await _rows(session, select(day, value).where(*conditions).group_by(day))


async def _sets(session: AsyncSession, scope: Scope, window: Window, metric: Metric) -> Daily:
    start, end = window.bounds(scope.zone)
    day = scope.local_date(WorkoutSet.completed_at)
    stmt = (
        select(day, SET_METRICS[metric]())
        .where(
            WorkoutSet.user_id == scope.user_id,
            WorkoutSet.is_warmup.is_(False),
            WorkoutSet.completed_at >= start,
            WorkoutSet.completed_at < end,
        )
        .group_by(day)
    )
    return await _rows(session, stmt)


async def _sessions(session: AsyncSession, scope: Scope, window: Window) -> Daily:
    start, end = window.bounds(scope.zone)
    day = scope.local_date(Workout.started_at)
    stmt = (
        select(day, func.count())
        .where(
            Workout.user_id == scope.user_id, Workout.started_at >= start, Workout.started_at < end
        )
        .group_by(day)
    )
    return await _rows(session, stmt)


async def daily(
    session: AsyncSession,
    scope: Scope,
    window: Window,
    metric: Metric,
    sport: SportGroup | None = None,
) -> Daily:
    if metric in SPORT_METRICS:
        return await _endurance(session, scope, window, metric, sport)
    if metric in SET_METRICS:
        return await _sets(session, scope, window, metric)
    if metric is Metric.SESSIONS:
        return await _sessions(session, scope, window)
    if metric in FOOD_METRICS:
        days = await food.daily(session, scope, window)
        return {d: getattr(totals, FOOD_METRICS[metric]) for d, totals in days.items()}
    if metric is Metric.WEIGHT:
        return await body.weights(session, scope, window.start, window.end)
    days_trained = await consistency.training_days(session, scope, window.start, window.end)
    return {d: t.minutes for d, t in days_trained.items()}


def bucketize(values: Daily, window: Window, bucket: Bucket, *, mean: bool) -> list[Point]:
    """One point per bucket overlapping the window: the sum (zero-filled) or the mean (None)."""
    grouped: dict[date, list[float]] = defaultdict(list)
    for day, value in values.items():
        if day in window:
            grouped[bucket_start(day, bucket)].append(value)
    points: list[Point] = []
    for start in bucket_starts(window, bucket):
        entries = grouped.get(start, [])
        if mean:
            points.append(Point(start, sum(entries) / len(entries) if entries else None))
        else:
            points.append(Point(start, sum(entries)))
    return points
