"""When the coach speaks (ADR 0030): the weekly schedule of program days, reminder stages and
quiet hours. Pure functions; the worker supplies the clock and the facts."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from trainsync.core.localtime import local_moment

# Program days without an explicit weekday (0 = Monday) follow this spread by days per week.
DEFAULT_WEEKDAYS: dict[int, tuple[int, ...]] = {
    1: (0,),
    2: (0, 3),
    3: (0, 2, 4),
    4: (0, 1, 3, 4),
    5: (0, 1, 2, 3, 4),
    6: (0, 1, 2, 3, 4, 5),
    7: (0, 1, 2, 3, 4, 5, 6),
}


@dataclass(frozen=True, slots=True)
class PlannedDay:
    day_id: int
    day_index: int
    name: str
    weekday: int | None
    start_time: time | None


def weekday_of(day: PlannedDay, days_per_week: int) -> int:
    """The day's own weekday, else its slot in the default spread (by `day_index`)."""
    if day.weekday is not None:
        return day.weekday
    spread = DEFAULT_WEEKDAYS[max(1, min(7, days_per_week))]
    return spread[day.day_index % len(spread)]


def scheduled_today(days: list[PlannedDay], days_per_week: int, today: date) -> PlannedDay | None:
    """The program day planned for `today`'s weekday (the first by index if several)."""
    for day in sorted(days, key=lambda d: d.day_index):
        if weekday_of(day, days_per_week) == today.weekday():
            return day
    return None


class Stage(StrEnum):
    BEFORE = "before"
    NOW = "now"
    NUDGE_30 = "nudge_30"
    NUDGE_90 = "nudge_90"
    MISSED = "missed"


STAGE_OFFSETS: dict[Stage, timedelta] = {
    Stage.BEFORE: timedelta(minutes=-30),
    Stage.NOW: timedelta(0),
    Stage.NUDGE_30: timedelta(minutes=30),
    Stage.NUDGE_90: timedelta(minutes=90),
    Stage.MISSED: timedelta(minutes=180),
}
# A stage still goes out this long after its moment (a worker that was briefly down); later
# than that it is skipped, never sent late.
GRACE = timedelta(minutes=15)


def due_stage(now: datetime, start: datetime, sent: set[Stage]) -> Stage | None:
    """The latest stage whose moment has passed within the grace window and was not sent."""
    for stage in reversed(Stage):
        moment = start + STAGE_OFFSETS[stage]
        if moment <= now < moment + GRACE:
            return None if stage in sent else stage
    return None


def start_moment(today: date, day: PlannedDay, default: time, zone: ZoneInfo) -> datetime:
    return local_moment(today, day.start_time or default, zone)


def is_quiet(moment: datetime, window: tuple[time, time], zone: ZoneInfo) -> bool:
    """Whether the local wall time of `moment` falls in the quiet window (may wrap midnight)."""
    start, end = window
    if start == end:
        return False
    local = moment.astimezone(zone).time()
    if start < end:
        return start <= local < end
    return local >= start or local < end
