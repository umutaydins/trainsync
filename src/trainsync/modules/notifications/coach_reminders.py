"""The reminder cron of the timed coach messages: today's scheduled program day gets a reminder
before and at its start, nudges, and a "missed" message, each only while no workout was started
that local day (ADR 0030)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.localtime import local_moment
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.context import using_context
from trainsync.modules.coach.packs import Key
from trainsync.modules.coach.schedule import (
    PlannedDay,
    Stage,
    due_stage,
    scheduled_today,
    start_moment,
)
from trainsync.modules.notifications.checkin import day_key
from trainsync.modules.notifications.coach_send import CoachDeps, send
from trainsync.modules.notifications.models import NotificationKind
from trainsync.modules.notifications.recipients import Recipient, recipients
from trainsync.modules.notifications.repository import NotificationRepository
from trainsync.modules.training.models import ProgramDay, Workout
from trainsync.modules.training.repository import ProgramRepository

STAGE_KINDS: dict[Stage, NotificationKind] = {
    Stage.BEFORE: NotificationKind.COACH_REMINDER_BEFORE,
    Stage.NOW: NotificationKind.COACH_REMINDER_NOW,
    Stage.NUDGE_30: NotificationKind.COACH_NUDGE_30,
    Stage.NUDGE_90: NotificationKind.COACH_NUDGE_90,
    Stage.MISSED: NotificationKind.COACH_MISSED,
}


async def _today_plan(
    session: AsyncSession, user_id: int, now: datetime, zone: ZoneInfo
) -> PlannedDay | None:
    """Today's scheduled day of the user's active program (local date), or None."""
    program = await ProgramRepository(session, user_id).active()
    if program is None:
        return None
    rows = await session.scalars(
        select(ProgramDay).where(ProgramDay.program_id == program.id, ProgramDay.user_id == user_id)
    )
    days = [PlannedDay(d.id, d.day_index, d.name, d.weekday, d.start_time) for d in rows.all()]
    return scheduled_today(days, program.days_per_week, now.astimezone(zone).date())


async def _started_today(
    session: AsyncSession, user_id: int, now: datetime, zone: ZoneInfo
) -> bool:
    today = now.astimezone(zone).date()
    start = local_moment(today, time(0, 0), zone)
    end = local_moment(today + timedelta(days=1), time(0, 0), zone)
    found = await session.scalar(
        select(Workout.id)
        .where(Workout.user_id == user_id, Workout.started_at >= start, Workout.started_at < end)
        .limit(1)
    )
    return found is not None


async def run_reminders(deps: CoachDeps) -> dict[int, str]:
    """One tick for every linked user: user id → outcome."""
    if deps.telegram is None:
        return {}
    outcomes = {}
    for who in await recipients(deps.sessionmaker, deps.settings):
        with using_context(who.context()):
            outcomes[who.user_id] = await reminders_for(deps, who)
    return outcomes


async def reminders_for(deps: CoachDeps, who: Recipient) -> str:
    """One user's tick. Outcome: disabled / no_plan / started / nothing / quiet / duplicate /
    sent / unknown / failed."""
    if deps.telegram is None:
        return "disabled"
    zone = who.settings.zone
    now = deps.clock()
    today = now.astimezone(zone).date()
    key = day_key(today)
    async with deps.sessionmaker() as session:
        day = await _today_plan(session, who.user_id, now, zone)
        if day is None:
            return "no_plan"
        if await _started_today(session, who.user_id, now, zone):
            return "started"
        notes = NotificationRepository(session, who.user_id)
        sent = {s for s, kind in STAGE_KINDS.items() if await notes.sent_at(kind, key)}
    start = start_moment(today, day, who.settings.workout_reminder_time, zone)
    stage = due_stage(now, start, sent)
    if stage is None:
        return "nothing"
    clock = f"{start.astimezone(zone):%H:%M}"
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
    return await send(deps, who, STAGE_KINDS[stage], key, text)
