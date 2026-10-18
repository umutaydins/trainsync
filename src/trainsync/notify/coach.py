"""Timed coach messages (P6.11, ADR 0030), sent by the worker to the notify chat.

- `coach_tick` (cron, every minute): today's scheduled program day (weekday, start time; the
  owner's local time `CHECKIN_TZ`) gets a reminder 30 min before, one at the start, nudges at
  +30 and +90 min and a "missed" message at +180 min, each only while no workout was started
  that local day and only within `GRACE` of its moment (never late).
- Jobs enqueued by the API: `coach_workout_started`, `coach_set_logged` (under target once per
  exercise; schedules `coach_rest_over` for the end of the planned rest), `coach_rest_over`
  (only if no newer set was logged and planned sets remain), `coach_workout_finished` (summary
  and verdict: PRs praised, misses roasted).

Every message claims a `notifications` row first (kind + local date / workout / set id), is
released after a definite send failure and kept after an unknown outcome, so retries, restarts
and duplicate jobs never repeat one. Nothing is sent in `QUIET_HOURS`; such a message is
dropped, not delayed.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from arq.connections import ArqRedis
from arq.cron import cron
from arq.worker import func
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.api.training.common import SetOut
from trainsync.api.training.workouts import WorkoutDetail, progression_rules, workout_detail
from trainsync.bot.common import client_id, kg, thousands
from trainsync.bot.formatting import duration
from trainsync.bot.messages import Key, Messages
from trainsync.bot.telegram import (
    TelegramApi,
    TelegramDeliveryUnknownError,
    TelegramError,
    TelegramRetryAfterError,
    TelegramUnavailableError,
)
from trainsync.bot.training import record_lines
from trainsync.coach.categories import Category
from trainsync.coach.schedule import (
    PlannedDay,
    Stage,
    due_stage,
    is_quiet,
    scheduled_today,
    start_moment,
)
from trainsync.coach.verdict import is_under_target, planned_for, target_weight, verdict
from trainsync.coach.voice import CoachVoice, build_voice
from trainsync.core.clock import Clock, Sleep
from trainsync.core.localtime import local_moment
from trainsync.core.logging import get_logger
from trainsync.core.metrics import NOTIFICATIONS
from trainsync.core.settings import Settings
from trainsync.db.models import NotificationKind, ProgramDay, Workout, WorkoutSet
from trainsync.db.repositories.notifications import NotificationRepository
from trainsync.db.repositories.training import ProgramRepository
from trainsync.notify.checkin import day_key
from trainsync.training.progression import Rules

log = get_logger(__name__)

COACH_CTX_KEY = "trainsync_coach"
DEFAULT_REST = timedelta(seconds=90)
# A rest-over job that runs later than this after its moment says nothing (sets logged after
# the fact, a worker that was down).
REST_LATE = timedelta(minutes=2)

STAGE_KINDS: dict[Stage, NotificationKind] = {
    Stage.BEFORE: NotificationKind.COACH_REMINDER_BEFORE,
    Stage.NOW: NotificationKind.COACH_REMINDER_NOW,
    Stage.NUDGE_30: NotificationKind.COACH_NUDGE_30,
    Stage.NUDGE_90: NotificationKind.COACH_NUDGE_90,
    Stage.MISSED: NotificationKind.COACH_MISSED,
}


@dataclass(frozen=True)
class CoachDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    telegram: TelegramApi | None  # None: timed coach messages off
    chat_id: int | None
    clock: Clock
    voice: CoachVoice
    msg: Messages
    zone: ZoneInfo
    default_start: time
    quiet: tuple[time, time]
    rules: Rules


def build_coach_deps(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    redis: Redis,
    clock: Clock,
    sleep: Sleep,
    msg: Messages,
) -> CoachDeps:
    telegram = None
    if settings.coach_active:
        telegram = TelegramApi(
            http,
            settings.telegram_bot_token,
            base_url=settings.telegram_api_base_url,
            sleep=sleep,
            max_attempts=2,
        )
    return CoachDeps(
        sessionmaker=sessionmaker,
        telegram=telegram,
        chat_id=settings.notify_chat_id(),
        clock=clock,
        voice=build_voice(settings, redis, msg),
        msg=msg,
        zone=settings.checkin_zone,
        default_start=settings.workout_reminder_time,
        quiet=settings.quiet_window,
        rules=progression_rules(settings),
    )


def under_target_key(workout_id: int, exercise_id: int) -> int:
    """Once per exercise per workout."""
    return workout_id * 100_000 + exercise_id


async def send(deps: CoachDeps, kind: NotificationKind, object_id: int, text: str) -> str:
    """Claim, send, and release after a definite failure. Outcome: disabled / quiet / duplicate
    / sent / unknown / failed."""
    if deps.telegram is None or deps.chat_id is None:
        return "disabled"
    now = deps.clock()
    if is_quiet(now, deps.quiet, deps.zone):
        log.info("coach_quiet_hours", kind=kind.value)
        return _count("quiet")
    async with deps.sessionmaker.begin() as session:
        claimed = await NotificationRepository(session).claim(kind, object_id, now)
    if not claimed:
        return _count("duplicate")
    try:
        await deps.telegram.send_message(deps.chat_id, text)
    except TelegramDeliveryUnknownError as exc:
        log.warning("coach_delivery_unknown", kind=kind.value, error=str(exc))
        return _count("unknown")
    except (TelegramError, TelegramRetryAfterError, TelegramUnavailableError) as exc:
        async with deps.sessionmaker.begin() as session:
            await NotificationRepository(session).release(kind, object_id)
        log.warning("coach_send_failed", kind=kind.value, error=str(exc))
        return _count("failed")
    log.info("coach_sent", kind=kind.value, object_id=object_id)
    return _count("sent")


def _count(outcome: str) -> str:
    NOTIFICATIONS.labels("telegram", f"coach_{outcome}").inc()
    return outcome


# ---------------------------------------------------------------- the reminder cron


async def _today_plan(session: AsyncSession, now: datetime, zone: ZoneInfo) -> PlannedDay | None:
    """Today's scheduled day of the active program (local date), or None."""
    program = await ProgramRepository(session).active()
    if program is None:
        return None
    rows = await session.scalars(select(ProgramDay).where(ProgramDay.program_id == program.id))
    days = [PlannedDay(d.id, d.day_index, d.name, d.weekday, d.start_time) for d in rows.all()]
    return scheduled_today(days, program.days_per_week, now.astimezone(zone).date())


async def _started_today(session: AsyncSession, now: datetime, zone: ZoneInfo) -> bool:
    today = now.astimezone(zone).date()
    start = local_moment(today, time(0, 0), zone)
    end = local_moment(today + timedelta(days=1), time(0, 0), zone)
    found = await session.scalar(
        select(Workout.id).where(Workout.started_at >= start, Workout.started_at < end).limit(1)
    )
    return found is not None


async def run_reminders(deps: CoachDeps) -> str:
    """One tick. Outcome: disabled / no_plan / started / nothing / quiet / duplicate / sent /
    unknown / failed."""
    if deps.telegram is None or deps.chat_id is None:
        return "disabled"
    now = deps.clock()
    today = now.astimezone(deps.zone).date()
    key = day_key(today)
    async with deps.sessionmaker() as session:
        day = await _today_plan(session, now, deps.zone)
        if day is None:
            return "no_plan"
        if await _started_today(session, now, deps.zone):
            return "started"
        notes = NotificationRepository(session)
        sent = {s for s, kind in STAGE_KINDS.items() if await notes.sent_at(kind, key)}
    start = start_moment(today, day, deps.default_start, deps.zone)
    stage = due_stage(now, start, sent)
    if stage is None:
        return "nothing"
    clock = f"{start.astimezone(deps.zone):%H:%M}"
    facts = [deps.msg(Key.COACH_FACT_SESSION, day=day.name, time=clock)]
    voice = deps.voice
    if stage is Stage.BEFORE:
        text = await voice.say(
            Category.REMINDER_BEFORE, Key.COACH_REMINDER_BEFORE, facts, day=day.name, time=clock
        )
    elif stage is Stage.NOW:
        text = await voice.say(
            Category.REMINDER_NOW, Key.COACH_REMINDER_NOW, facts, day=day.name, time=clock
        )
    elif stage is Stage.MISSED:
        text = await voice.say(Category.MISSED_WORKOUT, Key.COACH_MISSED, facts, day=day.name)
    else:
        text = await voice.say(
            Category.ESCALATION, Key.COACH_NUDGE, facts, day=day.name, time=clock
        )
    return await send(deps, STAGE_KINDS[stage], key, text)


async def coach_tick(ctx: dict[str, Any]) -> str:
    deps: CoachDeps = ctx[COACH_CTX_KEY]
    return await run_reminders(deps)


coach_cron = cron(coach_tick, name="coach_tick", minute=set(range(60)), run_at_startup=True)


# ---------------------------------------------------------------- workout events


async def _detail(deps: CoachDeps, workout_id: int) -> WorkoutDetail | None:
    async with deps.sessionmaker() as session:
        workout = await session.get(Workout, workout_id)
        if workout is None:
            return None
        return await workout_detail(session, workout, deps.rules)


def is_checkin_workout(deps: CoachDeps, detail: WorkoutDetail) -> bool:
    """Started by the evening check-in (its deterministic client id, P6.9): that conversation
    speaks for itself, so no live-workout messages for it."""
    day = detail.started_at.astimezone(deps.zone).date()
    return detail.client_id == client_id(f"checkin:{day.isoformat()}:workout")


def _live(deps: CoachDeps, detail: WorkoutDetail | None) -> WorkoutDetail | None:
    if detail is None or detail.ended_at is not None or is_checkin_workout(deps, detail):
        return None
    return detail


def _day_name(deps: CoachDeps, detail: WorkoutDetail) -> str:
    return detail.program_day_name or deps.msg(Key.COACH_FREE_WORKOUT)


async def workout_started(deps: CoachDeps, workout_id: int) -> str:
    detail = _live(deps, await _detail(deps, workout_id))
    if detail is None:
        return "skipped"
    name = _day_name(deps, detail)
    text = await deps.voice.say(Category.WORKOUT_START, Key.COACH_WORKOUT_START, [name], day=name)
    return await send(deps, NotificationKind.COACH_WORKOUT_START, workout_id, text)


def _set_text(logged: SetOut) -> str:
    load = "bw" if logged.weight_kg == 0 else kg(logged.weight_kg)
    return f"{load} x {logged.reps}"


async def set_logged(deps: CoachDeps, set_id: int, pool: ArqRedis | None) -> str:
    """Under target → one message per exercise per workout; then the rest-over job."""
    async with deps.sessionmaker() as session:
        row = await session.get(WorkoutSet, set_id)
    if row is None:
        return "skipped"
    detail = _live(deps, await _detail(deps, row.workout_id))
    if detail is None:
        return "skipped"
    logged = next((s for s in detail.sets if s.client_id == row.client_id), None)
    planned = planned_for(detail, row.exercise_id)
    outcome = "ok"
    if logged is not None and planned is not None and is_under_target(planned, logged):
        target = target_weight(planned)
        wanted = f"{'bw' if not target else kg(target)} x {planned.rep_min}"
        done = _set_text(logged)
        fields = {"exercise": planned.exercise.name, "done": done, "target": wanted}
        facts = [deps.msg(Key.COACH_FACT_UNDER, **fields)]
        text = await deps.voice.say(Category.UNDER_TARGET, Key.COACH_UNDER_TARGET, facts, **fields)
        key = under_target_key(row.workout_id, row.exercise_id)
        outcome = await send(deps, NotificationKind.COACH_UNDER_TARGET, key, text)
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
    detail = _live(deps, await _detail(deps, row.workout_id))
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
    return await send(deps, NotificationKind.COACH_REST_OVER, set_id, text)


async def workout_finished(deps: CoachDeps, workout_id: int) -> str:
    detail = await _detail(deps, workout_id)
    if detail is None or detail.ended_at is None or is_checkin_workout(deps, detail):
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
    return await send(deps, NotificationKind.COACH_WORKOUT_DONE, workout_id, text)


async def coach_workout_started(ctx: dict[str, Any], workout_id: int) -> str:
    return await workout_started(ctx[COACH_CTX_KEY], workout_id)


async def coach_set_logged(ctx: dict[str, Any], set_id: int) -> str:
    return await set_logged(ctx[COACH_CTX_KEY], set_id, ctx.get("redis"))


async def coach_rest_over(ctx: dict[str, Any], set_id: int) -> str:
    return await rest_over(ctx[COACH_CTX_KEY], set_id)


async def coach_workout_finished(ctx: dict[str, Any], workout_id: int) -> str:
    return await workout_finished(ctx[COACH_CTX_KEY], workout_id)


COACH_JOBS = [
    func(coach_workout_started, name="coach_workout_started", max_tries=3),
    func(coach_set_logged, name="coach_set_logged", max_tries=3),
    func(coach_rest_over, name="coach_rest_over", max_tries=3),
    func(coach_workout_finished, name="coach_workout_finished", max_tries=3),
]
