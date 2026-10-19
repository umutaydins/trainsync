"""Consistency: active days, streaks, check-in completion and the year heatmap (ADR 0038).

A training day has at least one activity or workout (local day). The training streak counts ISO
weeks in a row with a training day — a rest day must not break the habit — and, like the check-in
streak (ADR 0020), the current week still counts while it has none yet.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.checkin import streaks
from trainsync.modules.checkin.models import CheckinStatus
from trainsync.modules.checkin.repository import CheckinRepository
from trainsync.modules.stats.periods import Window
from trainsync.modules.stats.scope import Scope
from trainsync.modules.training.models import Workout

SECONDS_PER_MINUTE = 60
WEEK = timedelta(7)


@dataclass(slots=True)
class TrainingDay:
    sessions: int = 0
    minutes: float = 0.0


@dataclass(frozen=True, slots=True)
class Consistency:
    active_days: int
    training_streak_weeks: int
    longest_training_streak_weeks: int
    checkin_streak_days: int
    longest_checkin_streak_days: int
    checkin_days: int
    window_days: int

    @property
    def checkin_rate(self) -> float | None:
        return self.checkin_days / self.window_days if self.window_days else None


async def training_days(
    session: AsyncSession, scope: Scope, start: date, end: date
) -> dict[date, TrainingDay]:
    """Sessions and minutes per local day: activities (moving time) and workouts (duration)."""
    window = Window(start, end)
    lower, upper = window.bounds(scope.zone)
    day = scope.local_date(Activity.start_date)
    activities = (
        select(day, func.count(), func.sum(Activity.moving_time_s))
        .where(
            Activity.user_id == scope.user_id,
            Activity.athlete_id.in_(scope.athlete_ids),
            Activity.deleted_at.is_(None),
            Activity.start_date >= lower,
            Activity.start_date < upper,
        )
        .group_by(day)
    )
    workout_day = scope.local_date(Workout.started_at)
    duration = func.coalesce(extract("epoch", Workout.ended_at - Workout.started_at), 0)
    workouts = (
        select(workout_day, func.count(), func.sum(duration))
        .where(
            Workout.user_id == scope.user_id,
            Workout.started_at >= lower,
            Workout.started_at < upper,
        )
        .group_by(workout_day)
    )
    days: dict[date, TrainingDay] = defaultdict(TrainingDay)
    for stmt in (activities, workouts):
        for local_day, sessions, seconds in (await session.execute(stmt)).all():
            days[local_day].sessions += sessions
            days[local_day].minutes += float(seconds or 0) / SECONDS_PER_MINUTE
    return dict(sorted(days.items()))


def _monday(day: date) -> date:
    return day - timedelta(day.weekday())


def week_streaks(days: set[date], today: date) -> tuple[int, int]:
    """(current, longest) runs of consecutive ISO weeks with a training day."""
    weeks = sorted({_monday(d) for d in days if d <= today})
    longest = run = 0
    previous: date | None = None
    for monday in weeks:
        run = run + 1 if previous is not None and monday - previous == WEEK else 1
        longest, previous = max(longest, run), monday
    week = _monday(today) if _monday(today) in weeks else _monday(today) - WEEK
    current = 0
    while week in weeks:
        current, week = current + 1, week - WEEK
    return current, longest


async def consistency(
    session: AsyncSession, scope: Scope, window: Window, first_day: date, today: date
) -> Consistency:
    history = await training_days(session, scope, min(first_day, window.start), today)
    current, longest = week_streaks(set(history), today)
    statuses = await CheckinRepository(session, scope.user_id).statuses(today)
    return Consistency(
        active_days=sum(1 for d in history if d in window),
        training_streak_weeks=current,
        longest_training_streak_weeks=longest,
        checkin_streak_days=streaks.current_streak(statuses, today),
        longest_checkin_streak_days=streaks.longest_streak(statuses, today),
        checkin_days=sum(1 for d in statuses if d in window),
        window_days=window.days,
    )


@dataclass(frozen=True, slots=True)
class HeatmapDay:
    day: date
    sessions: int
    minutes: float
    checkin: CheckinStatus | None


async def heatmap(session: AsyncSession, scope: Scope, year: int) -> list[HeatmapDay]:
    """One entry per local day of `year`, zero-filled."""
    window = Window(date(year, 1, 1), date(year, 12, 31))
    days = await training_days(session, scope, window.start, window.end)
    checkins = {
        c.date: CheckinStatus(c.status)
        for c in await CheckinRepository(session, scope.user_id).between(window.start, window.end)
    }
    result: list[HeatmapDay] = []
    for offset in range(window.days):
        day = window.start + timedelta(offset)
        training = days.get(day, TrainingDay())
        result.append(HeatmapDay(day, training.sessions, training.minutes, checkins.get(day)))
    return result
