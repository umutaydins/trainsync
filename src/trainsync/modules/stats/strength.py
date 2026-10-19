"""Strength statistics from logged workouts (P8.10, ADR 0038).

Working sets only (warm-ups never count). e1RM is Epley over sets of 1..`max_reps` reps; a PR is
a workout whose best e1RM for a lift is strictly above every earlier workout's.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Numeric, and_, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.stats.periods import Window
from trainsync.modules.stats.scope import Scope
from trainsync.modules.training.models import Exercise, Workout, WorkoutSet

EPLEY_REPS_DIVISOR = 30


@dataclass(frozen=True, slots=True)
class StrengthTotals:
    sessions: int
    sets: int
    reps: int
    tonnage_kg: Decimal


@dataclass(frozen=True, slots=True)
class MuscleTotals:
    muscle: str
    sets: int
    tonnage_kg: Decimal


@dataclass(frozen=True, slots=True)
class ExerciseTotals:
    exercise_id: int
    name: str
    muscle: str
    sets: int
    reps: int
    tonnage_kg: Decimal
    best_e1rm_kg: Decimal | None


@dataclass(frozen=True, slots=True)
class PrEvent:
    exercise_id: int
    name: str
    workout_id: int
    achieved_at: datetime
    e1rm_kg: Decimal
    previous_kg: Decimal | None


def e1rm_column(max_reps: int) -> ColumnElement[Any]:
    """Epley in SQL, rounded to 0.01 kg; NULL outside 1..`max_reps` reps or for a warm-up."""
    weight, reps = WorkoutSet.weight_kg, WorkoutSet.reps
    return case(
        (WorkoutSet.is_warmup | (reps < 1) | (reps > max_reps), None),
        (reps == 1, weight),
        else_=func.round(cast(weight * (1 + reps / cast(EPLEY_REPS_DIVISOR, Numeric)), Numeric), 2),
    )


def _set_conditions(scope: Scope, window: Window) -> list[ColumnElement[bool]]:
    start, end = window.bounds(scope.zone)
    return [
        WorkoutSet.user_id == scope.user_id,
        WorkoutSet.completed_at >= start,
        WorkoutSet.completed_at < end,
        WorkoutSet.is_warmup.is_(False),
    ]


def _tonnage() -> ColumnElement[Any]:
    return func.coalesce(func.sum(WorkoutSet.reps * WorkoutSet.weight_kg), 0)


async def totals(session: AsyncSession, scope: Scope, window: Window) -> StrengthTotals:
    start, end = window.bounds(scope.zone)
    sessions = await session.scalar(
        select(func.count()).where(
            Workout.user_id == scope.user_id, Workout.started_at >= start, Workout.started_at < end
        )
    )
    row = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(WorkoutSet.reps), 0), _tonnage()).where(
                *_set_conditions(scope, window)
            )
        )
    ).one()
    return StrengthTotals(sessions or 0, row[0], int(row[1]), Decimal(row[2]))


async def per_muscle(session: AsyncSession, scope: Scope, window: Window) -> list[MuscleTotals]:
    stmt = (
        select(Exercise.primary_muscle, func.count(), _tonnage())
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .where(*_set_conditions(scope, window))
        .group_by(Exercise.primary_muscle)
        .order_by(_tonnage().desc(), Exercise.primary_muscle)
    )
    return [MuscleTotals(r[0], r[1], Decimal(r[2])) for r in (await session.execute(stmt)).all()]


async def per_exercise(
    session: AsyncSession, scope: Scope, window: Window, max_reps: int
) -> list[ExerciseTotals]:
    stmt = (
        select(
            Exercise.id,
            Exercise.name,
            Exercise.primary_muscle,
            func.count(),
            func.coalesce(func.sum(WorkoutSet.reps), 0),
            _tonnage(),
            func.max(e1rm_column(max_reps)),
        )
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .where(*_set_conditions(scope, window))
        .group_by(Exercise.id, Exercise.name, Exercise.primary_muscle)
        .order_by(_tonnage().desc(), Exercise.name)
    )
    return [
        ExerciseTotals(r[0], r[1], r[2], r[3], int(r[4]), Decimal(r[5]), r[6])
        for r in (await session.execute(stmt)).all()
    ]


async def pr_events(
    session: AsyncSession,
    scope: Scope,
    max_reps: int,
    window: Window | None = None,
    exercise_id: int | None = None,
) -> list[PrEvent]:
    """Every e1RM record of the user, oldest first; only those inside `window` if given.

    The best e1RM per (lift, workout) is compared with the running maximum of all earlier
    workouts of that lift, in one window-function query over the whole history.
    """
    conditions = [WorkoutSet.user_id == scope.user_id]
    if exercise_id is not None:
        conditions.append(WorkoutSet.exercise_id == exercise_id)
    best = (
        select(
            WorkoutSet.exercise_id.label("exercise_id"),
            WorkoutSet.workout_id.label("workout_id"),
            func.min(WorkoutSet.completed_at).label("achieved_at"),
            func.max(e1rm_column(max_reps)).label("e1rm"),
        )
        .where(*conditions)
        .group_by(WorkoutSet.exercise_id, WorkoutSet.workout_id)
        .subquery()
    )
    earlier = (
        func.max(best.c.e1rm)
        .over(
            partition_by=best.c.exercise_id,
            order_by=(best.c.achieved_at, best.c.workout_id),
            rows=(None, -1),
        )
        .label("previous")
    )
    ranked = select(best, earlier).where(best.c.e1rm.is_not(None)).subquery()
    record = and_(ranked.c.e1rm > func.coalesce(ranked.c.previous, 0))
    stmt = (
        select(
            ranked.c.exercise_id,
            Exercise.name,
            ranked.c.workout_id,
            ranked.c.achieved_at,
            ranked.c.e1rm,
            ranked.c.previous,
        )
        .join(Exercise, Exercise.id == ranked.c.exercise_id)
        .where(record)
        .order_by(ranked.c.achieved_at, ranked.c.workout_id, ranked.c.exercise_id)
    )
    if window is not None:
        start, end = window.bounds(scope.zone)
        stmt = stmt.where(ranked.c.achieved_at >= start, ranked.c.achieved_at < end)
    return [PrEvent(*r) for r in (await session.execute(stmt)).all()]


async def workout_counts(
    session: AsyncSession, scope: Scope, window: Window, program_day_ids: list[int]
) -> tuple[int, int]:
    """(workouts, working sets) of the window logged against the given program days."""
    if not program_day_ids:
        return 0, 0
    start, end = window.bounds(scope.zone)
    row = (
        await session.execute(
            select(func.count(distinct(Workout.id)), func.count(WorkoutSet.id))
            .select_from(Workout)
            .outerjoin(
                WorkoutSet,
                and_(WorkoutSet.workout_id == Workout.id, WorkoutSet.is_warmup.is_(False)),
            )
            .where(
                Workout.user_id == scope.user_id,
                Workout.program_day_id.in_(program_day_ids),
                Workout.started_at >= start,
                Workout.started_at < end,
            )
        )
    ).one()
    return row[0], row[1]
