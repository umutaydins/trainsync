"""The progress statistics of one user for one period (P8.10, ADR 0038)."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.checkin.models import DailyCheckin
from trainsync.modules.nutrition.models import FoodLog
from trainsync.modules.stats import adherence, body, consistency, endurance, food, strength
from trainsync.modules.stats.periods import Resolved, Window
from trainsync.modules.stats.schemas import (
    AdherenceOut,
    BodyOut,
    ConsistencyOut,
    EffortOut,
    EnduranceOut,
    EnduranceTotalsOut,
    ExerciseProgressOut,
    MuscleProgressOut,
    NutritionOut,
    ProgressOut,
    SportGroupOut,
    StrengthOut,
    WindowOut,
    change,
)
from trainsync.modules.stats.scope import Scope
from trainsync.modules.training.models import BodyMetric, Workout


@dataclass(frozen=True, slots=True)
class StatsContext:
    session: AsyncSession
    scope: Scope
    today: date
    sugar_limit_g: float
    e1rm_max_reps: int


async def first_day(session: AsyncSession, scope: Scope) -> date | None:
    """The user's first local day with any data (the start of `all`)."""
    starts = union_all(
        select(func.min(scope.local_date(Activity.start_date))).where(
            Activity.user_id == scope.user_id, Activity.deleted_at.is_(None)
        ),
        select(func.min(scope.local_date(Workout.started_at))).where(
            Workout.user_id == scope.user_id
        ),
        select(func.min(FoodLog.date)).where(FoodLog.user_id == scope.user_id),
        select(func.min(BodyMetric.date)).where(BodyMetric.user_id == scope.user_id),
        select(func.min(DailyCheckin.date)).where(DailyCheckin.user_id == scope.user_id),
    ).subquery()
    first: date | None = await session.scalar(select(func.min(starts.c[0])))
    return first


def _endurance_totals(
    now: endurance.GroupTotals, before: endurance.GroupTotals | None, compared: bool
) -> dict[str, object]:
    def pick(attr: str) -> tuple[float | None, float | None]:
        return getattr(now, attr), getattr(before, attr) if before is not None else 0

    fields = ("count", "distance_m", "moving_time_s", "elevation_gain_m")
    values: dict[str, object] = {f: change(*pick(f), compared) for f in fields}
    previous_speed = before.average_speed_mps if before is not None else None
    previous_hr = before.average_heartrate if before is not None else None
    values["average_speed_mps"] = change(now.average_speed_mps, previous_speed, compared)
    values["average_heartrate"] = change(now.average_heartrate, previous_hr, compared)
    return values


async def _endurance(ctx: StatsContext, resolved: Resolved) -> EnduranceOut:
    current = await endurance.endurance(ctx.session, ctx.scope, resolved.window)
    previous: list[endurance.GroupTotals] = []
    if resolved.previous is not None:
        previous = await endurance.group_totals(ctx.session, ctx.scope, resolved.previous)
    before = {g.group: g for g in previous}
    compared = resolved.previous is not None
    total_before = endurance.Endurance(previous, [], []).total()
    return EnduranceOut(
        totals=EnduranceTotalsOut.model_validate(
            _endurance_totals(current.total(), total_before, compared)
        ),
        by_group=[
            SportGroupOut.model_validate(
                {"group": g.group, **_endurance_totals(g, before.get(g.group), compared)}
            )
            for g in current.groups
        ],
        longest=[_effort(e) for e in current.longest],
        fastest=[_effort(e) for e in current.fastest],
    )


def _effort(effort: endurance.Effort) -> EffortOut:
    return EffortOut(
        group=effort.group,
        activity_id=effort.activity_id,
        name=effort.name,
        start_date=effort.start_date,
        distance_m=effort.distance_m,
        moving_time_s=effort.moving_time_s,
        average_speed_mps=effort.average_speed_mps,
    )


async def _strength(ctx: StatsContext, resolved: Resolved) -> StrengthOut:
    session, scope, window = ctx.session, ctx.scope, resolved.window
    now = await strength.totals(session, scope, window)
    records = await strength.pr_events(session, scope, ctx.e1rm_max_reps, window)
    before, before_records, best_before = None, 0, {}
    if resolved.previous is not None:
        before = await strength.totals(session, scope, resolved.previous)
        before_records = len(
            await strength.pr_events(session, scope, ctx.e1rm_max_reps, resolved.previous)
        )
        best_before = {
            e.exercise_id: e.best_e1rm_kg
            for e in await strength.per_exercise(
                session, scope, resolved.previous, ctx.e1rm_max_reps
            )
        }
    compared = before is not None

    def pair(attr: str) -> tuple[float, float | None]:
        return float(getattr(now, attr)), float(getattr(before, attr)) if before else None

    plan = await adherence.adherence(session, scope, window)
    exercises = await strength.per_exercise(session, scope, window, ctx.e1rm_max_reps)
    return StrengthOut(
        sessions=change(*pair("sessions"), compared),
        sets=change(*pair("sets"), compared),
        reps=change(*pair("reps"), compared),
        tonnage_kg=change(*pair("tonnage_kg"), compared),
        pr_count=change(len(records), before_records, compared),
        by_muscle=[
            MuscleProgressOut(muscle=m.muscle, sets=m.sets, tonnage_kg=float(m.tonnage_kg))
            for m in await strength.per_muscle(session, scope, window)
        ],
        by_exercise=[
            ExerciseProgressOut(
                exercise_id=e.exercise_id,
                name=e.name,
                muscle=e.muscle,
                sets=e.sets,
                reps=e.reps,
                tonnage_kg=float(e.tonnage_kg),
                best_e1rm_kg=change(
                    _float(e.best_e1rm_kg), _float(best_before.get(e.exercise_id)), compared
                ),
            )
            for e in exercises
        ],
        adherence=None
        if plan is None
        else AdherenceOut(
            program_id=plan.program_id,
            program_name=plan.program_name,
            planned_sessions=plan.planned_sessions,
            done_sessions=plan.done_sessions,
            planned_sets=plan.planned_sets,
            done_sets=plan.done_sets,
            session_ratio=plan.session_ratio,
            set_ratio=plan.set_ratio,
        ),
    )


def _float(value: object) -> float | None:
    return None if value is None else float(str(value))


async def _consistency(ctx: StatsContext, resolved: Resolved, first: date) -> ConsistencyOut:
    now = await consistency.consistency(ctx.session, ctx.scope, resolved.window, first, ctx.today)
    before = None
    if resolved.previous is not None:
        before = await consistency.consistency(
            ctx.session, ctx.scope, resolved.previous, first, ctx.today
        )
    compared = before is not None
    return ConsistencyOut(
        active_days=change(now.active_days, before.active_days if before else None, compared),
        training_streak_weeks=now.training_streak_weeks,
        longest_training_streak_weeks=now.longest_training_streak_weeks,
        checkin_streak_days=now.checkin_streak_days,
        longest_checkin_streak_days=now.longest_checkin_streak_days,
        checkin_rate=change(now.checkin_rate, before.checkin_rate if before else None, compared),
        sick_days=now.sick_days,
    )


async def _nutrition(ctx: StatsContext, resolved: Resolved) -> NutritionOut:
    now = await food.nutrition(ctx.session, ctx.scope, resolved.window, ctx.sugar_limit_g)
    before = None
    if resolved.previous is not None:
        before = await food.nutrition(ctx.session, ctx.scope, resolved.previous, ctx.sugar_limit_g)
    compared = before is not None

    def pair(attr: str) -> tuple[float | None, float | None]:
        return getattr(now, attr), getattr(before, attr) if before else None

    averages = ("avg_kcal", "avg_protein_g", "avg_carbs_g", "avg_fat_g")
    counts = ("logged_days", "logging_rate", "days_over_sugar_limit")
    return NutritionOut.model_validate(
        {
            **{name: change(*pair(name), compared) for name in (*averages, *counts)},
            "kcal_target": now.kcal_target,
            "sugar_limit_g": ctx.sugar_limit_g,
        }
    )


async def _body(ctx: StatsContext, resolved: Resolved) -> BodyOut:
    now = await body.body(ctx.session, ctx.scope, resolved.window)
    before = None
    if resolved.previous is not None:
        before = await body.body(ctx.session, ctx.scope, resolved.previous)
    compared = before is not None
    return BodyOut(
        first_kg=now.first_kg,
        last_kg=now.last_kg,
        change_kg=change(now.change_kg, before.change_kg if before else None, compared),
        moving_average_kg=now.points[-1].moving_average_kg if now.points else None,
        rate_kg_per_week=change(
            now.rate_kg_per_week, before.rate_kg_per_week if before else None, compared
        ),
        body_fat_pct=now.body_fat_pct,
    )


async def progress(ctx: StatsContext, resolved: Resolved, first: date | None) -> ProgressOut:
    previous: Window | None = resolved.previous
    return ProgressOut(
        period=resolved.period,
        timezone=ctx.scope.zone.key,
        window=WindowOut.of(resolved.window),
        previous=None if previous is None else WindowOut.of(previous),
        endurance=await _endurance(ctx, resolved),
        strength=await _strength(ctx, resolved),
        consistency=await _consistency(ctx, resolved, first or resolved.window.start),
        nutrition=await _nutrition(ctx, resolved),
        body=await _body(ctx, resolved),
    )
