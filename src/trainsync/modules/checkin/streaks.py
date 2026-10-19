"""Check-in streaks and adherence (P6.9, ADR 0020). Pure functions over `date → status`.

- **Streak**: consecutive local days with a check-in that is not `skipped` (done, partial, rest
  and sick/injured all count: showing up and being honest is the habit). A missing day or a
  `skipped` day breaks it. The current streak ends on `today`, or on yesterday while today has no
  check-in yet (the day is not over).
- **Adherence** = planned days done / planned days, per ISO week inside the range:
  planned = min(days_per_week of the active program, days of that week inside the range minus
  sick/injured days), never below 0; done = done + partial days, at most `planned`. Without an
  active program nothing is planned and adherence is unknown (`None`), not 0 %.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from trainsync.modules.checkin.models import CheckinStatus

COUNTS_FOR_STREAK = frozenset(
    {
        CheckinStatus.DONE,
        CheckinStatus.PARTIAL,
        CheckinStatus.REST,
        CheckinStatus.SICK_OR_INJURED,
    }
)
TRAINED = frozenset({CheckinStatus.DONE, CheckinStatus.PARTIAL})

Statuses = Mapping[date, CheckinStatus]


def current_streak(statuses: Statuses, today: date) -> int:
    day = today if today in statuses else today - timedelta(days=1)
    streak = 0
    while statuses.get(day) in COUNTS_FOR_STREAK:
        streak += 1
        day -= timedelta(days=1)
    return streak


def longest_streak(statuses: Statuses, until: date) -> int:
    best = run = 0
    previous: date | None = None
    for day in sorted(d for d in statuses if d <= until):
        if statuses[day] not in COUNTS_FOR_STREAK:
            run, previous = 0, None
            continue
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        previous = day
        best = max(best, run)
    return best


@dataclass(frozen=True, slots=True)
class WeekAdherence:
    week_start: date  # Monday
    planned: int
    done: int


@dataclass(frozen=True, slots=True)
class Adherence:
    planned: int
    done: int
    weeks: list[WeekAdherence]

    @property
    def ratio(self) -> float | None:
        return None if self.planned == 0 else self.done / self.planned


def adherence(statuses: Statuses, start: date, end: date, days_per_week: int | None) -> Adherence:
    weeks: list[WeekAdherence] = []
    monday = start - timedelta(days=start.weekday())
    while monday <= end:
        days = [
            monday + timedelta(days=i)
            for i in range(7)
            if start <= monday + timedelta(days=i) <= end
        ]
        sick = sum(1 for d in days if statuses.get(d) == CheckinStatus.SICK_OR_INJURED)
        planned = max(0, min(days_per_week or 0, len(days) - sick))
        trained = sum(1 for d in days if statuses.get(d) in TRAINED)
        weeks.append(WeekAdherence(monday, planned, min(planned, trained)))
        monday += timedelta(days=7)
    return Adherence(sum(w.planned for w in weeks), sum(w.done for w in weeks), weeks)
