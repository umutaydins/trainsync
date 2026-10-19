"""Coach messages on workout events, enqueued by the API (ADR 0030): workout started, set under
target (then the rest-over job), rest over, workout finished (summary and verdict)."""

from datetime import timedelta

from arq.connections import ArqRedis
from sqlalchemy import select

from trainsync.modules.chat.common import client_id, kg, thousands
from trainsync.modules.chat.formatting import duration
from trainsync.modules.chat.training import record_lines
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.context import using_context
from trainsync.modules.coach.packs import Key
from trainsync.modules.coach.verdict import is_under_target, planned_for, target_weight, verdict
from trainsync.modules.notifications.coach_send import CoachDeps, send
from trainsync.modules.notifications.models import NotificationKind
from trainsync.modules.notifications.recipients import Recipient, recipient
from trainsync.modules.training.models import Workout, WorkoutSet
from trainsync.modules.training.schemas import SetOut
from trainsync.modules.training.workout_detail import workout_detail
from trainsync.modules.training.workout_schemas import WorkoutDetail

DEFAULT_REST = timedelta(seconds=90)
# A rest-over job that runs later than this after its moment says nothing (sets logged after
# the fact, a worker that was down).
REST_LATE = timedelta(minutes=2)
# under_target_key = workout id x this + exercise id: unique while exercise ids stay below it.
UNDER_TARGET_KEY_BASE = 100_000
BODYWEIGHT_LABEL = "bw"


def under_target_key(workout_id: int, exercise_id: int) -> int:
    """Once per exercise per workout."""
    return workout_id * UNDER_TARGET_KEY_BASE + exercise_id


async def _workout_owner(deps: CoachDeps, workout_id: int) -> Recipient | None:
    """The linked chat of the workout's user (jobs are keyed by workout id)."""
    async with deps.sessionmaker() as session:
        user_id = await session.scalar(select(Workout.user_id).where(Workout.id == workout_id))
    if user_id is None:
        return None
    return await recipient(deps.sessionmaker, deps.settings, user_id)


async def _detail(deps: CoachDeps, who: Recipient, workout_id: int) -> WorkoutDetail | None:
    async with deps.sessionmaker() as session:
        workout = await session.get(Workout, workout_id)
        if workout is None or workout.user_id != who.user_id:
            return None
        return await workout_detail(session, who.user_id, workout, deps.rules)


def is_checkin_workout(who: Recipient, detail: WorkoutDetail) -> bool:
    """Started by the evening check-in (its deterministic client id, P6.9): that conversation
    speaks for itself, so no live-workout messages for it."""
    day = detail.started_at.astimezone(who.settings.zone).date()
    return detail.client_id == client_id(f"checkin:{day.isoformat()}:workout")


def _live(who: Recipient, detail: WorkoutDetail | None) -> WorkoutDetail | None:
    if detail is None or detail.ended_at is not None or is_checkin_workout(who, detail):
        return None
    return detail


def _day_name(deps: CoachDeps, detail: WorkoutDetail) -> str:
    return detail.program_day_name or deps.msg(Key.COACH_FREE_WORKOUT)


async def workout_started(deps: CoachDeps, workout_id: int) -> str:
    who = await _workout_owner(deps, workout_id)
    if who is None:
        return "disabled"
    with using_context(who.context()):
        detail = _live(who, await _detail(deps, who, workout_id))
        if detail is None:
            return "skipped"
        name = _day_name(deps, detail)
        text = await deps.voice.say(
            Category.WORKOUT_START, Key.COACH_WORKOUT_START, [name], day=name
        )
        return await send(deps, who, NotificationKind.COACH_WORKOUT_START, workout_id, text)


def _set_text(logged: SetOut) -> str:
    load = BODYWEIGHT_LABEL if logged.weight_kg == 0 else kg(logged.weight_kg)
    return f"{load} x {logged.reps}"


async def set_logged(deps: CoachDeps, set_id: int, pool: ArqRedis | None) -> str:
    """Under target → one message per exercise per workout; then the rest-over job."""
    async with deps.sessionmaker() as session:
        row = await session.get(WorkoutSet, set_id)
    if row is None:
        return "skipped"
    who = await _workout_owner(deps, row.workout_id)
    if who is None:
        return "disabled"
    with using_context(who.context()):
        return await _set_logged(deps, who, row, pool)


async def _set_logged(
    deps: CoachDeps, who: Recipient, row: WorkoutSet, pool: ArqRedis | None
) -> str:
    set_id = row.id
    detail = _live(who, await _detail(deps, who, row.workout_id))
    if detail is None:
        return "skipped"
    logged = next((s for s in detail.sets if s.client_id == row.client_id), None)
    planned = planned_for(detail, row.exercise_id)
    outcome = "ok"
    if logged is not None and planned is not None and is_under_target(planned, logged):
        target = target_weight(planned)
        wanted = f"{BODYWEIGHT_LABEL if not target else kg(target)} x {planned.rep_min}"
        done = _set_text(logged)
        fields = {"exercise": planned.exercise.name, "done": done, "target": wanted}
        facts = [deps.msg(Key.COACH_FACT_UNDER, **fields)]
        text = await deps.voice.say(Category.UNDER_TARGET, Key.COACH_UNDER_TARGET, facts, **fields)
        key = under_target_key(row.workout_id, row.exercise_id)
        outcome = await send(deps, who, NotificationKind.COACH_UNDER_TARGET, key, text)
    if pool is not None and logged is not None and not logged.is_warmup:
        rest = timedelta(seconds=planned.rest_seconds) if planned else DEFAULT_REST
        await pool.enqueue_job(
            "coach_rest_over",
            set_id,
            _job_id=f"coach_rest:{set_id}",
            _defer_until=row.completed_at + rest,
        )
    return outcome


async def rest_over(deps: CoachDeps, set_id: int) -> str:
    async with deps.sessionmaker() as session:
        row = await session.get(WorkoutSet, set_id)
    if row is None:
        return "skipped"
    who = await _workout_owner(deps, row.workout_id)
    if who is None:
        return "disabled"
    with using_context(who.context()):
        return await _rest_over(deps, who, row)


async def _rest_over(deps: CoachDeps, who: Recipient, row: WorkoutSet) -> str:
    set_id = row.id
    detail = _live(who, await _detail(deps, who, row.workout_id))
    if detail is None:
        return "skipped"
    planned = planned_for(detail, row.exercise_id)
    due = row.completed_at + (timedelta(seconds=planned.rest_seconds) if planned else DEFAULT_REST)
    if deps.clock() > due + REST_LATE:
        return "late"
    latest = max(detail.sets, key=lambda s: (s.completed_at, s.set_index), default=None)
    if latest is None or latest.client_id != row.client_id:
        return "superseded"  # a newer set was logged: its own rest is what counts
    if detail.planned and verdict(detail).missing_sets == 0:
        return "all_done"
    text = await deps.voice.say(Category.REST_OVER, Key.COACH_REST_OVER, [])
    return await send(deps, who, NotificationKind.COACH_REST_OVER, set_id, text)


async def workout_finished(deps: CoachDeps, workout_id: int) -> str:
    who = await _workout_owner(deps, workout_id)
    if who is None:
        return "disabled"
    with using_context(who.context()):
        return await _workout_finished(deps, who, workout_id)


async def _workout_finished(deps: CoachDeps, who: Recipient, workout_id: int) -> str:
    detail = await _detail(deps, who, workout_id)
    if detail is None or detail.ended_at is None or is_checkin_workout(who, detail):
        return "skipped"
    msg = deps.msg
    summary = msg(
        Key.DONE_SUMMARY,
        count=detail.set_count,
        exercises=detail.exercise_count,
        volume=thousands(detail.volume_kg),
        duration=duration(int((detail.ended_at - detail.started_at).total_seconds())),
    )
    result = verdict(detail)
    facts = [summary, *record_lines(detail.records, msg)]
    if result.good:
        line = await deps.voice.line(Category.WORKOUT_DONE_GOOD, Key.COACH_DONE_GOOD)
    else:
        if result.missing_sets:
            facts.append(msg(Key.COACH_FACT_MISSING, missing=result.missing_sets))
        line = await deps.voice.line(
            Category.WORKOUT_DONE_BAD, Key.COACH_DONE_BAD, missing=result.missing_sets
        )
    text = "\n".join([*facts, line])
    return await send(deps, who, NotificationKind.COACH_WORKOUT_DONE, workout_id, text)
