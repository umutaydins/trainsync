"""Program adherence: planned vs done sessions and sets of the active program (ADR 0038).

Planned sessions are counted from the day the program was created (local): each program day
with a weekday is planned on that weekday; without weekdays the program plans `days_per_week`
sessions per ISO week, fewer in a week the window only partly covers. A planned session plans
the sets of its program day (without weekdays: the program's mean sets per day).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.stats.periods import Window
from trainsync.modules.stats.scope import Scope
from trainsync.modules.stats.strength import workout_counts
from trainsync.modules.training.repository import ProgramRepository, ProgramTree

DAYS_PER_WEEK = 7


@dataclass(frozen=True, slots=True)
class Adherence:
    program_id: int
    program_name: str
    planned_sessions: int
    done_sessions: int
    planned_sets: int
    done_sets: int

    @property
    def session_ratio(self) -> float | None:
        if not self.planned_sessions:
            return None
        return min(1.0, self.done_sessions / self.planned_sessions)

    @property
    def set_ratio(self) -> float | None:
        return min(1.0, self.done_sets / self.planned_sets) if self.planned_sets else None


def _days(window: Window) -> list[date]:
    return [window.start + timedelta(i) for i in range(window.days)]


def planned(tree: ProgramTree, window: Window) -> tuple[int, int]:
    """(sessions, sets) the program plans inside the window."""
    sets_of = {day.id: sum(e.sets for e in exercises) for day, exercises in tree.days}
    with_weekday = [day for day, _ in tree.days if day.weekday is not None]
    days = _days(window)
    if with_weekday:
        sessions = [d for day in with_weekday for d in days if d.weekday() == day.weekday]
        return len(sessions), sum(
            sets_of[day.id] for day in with_weekday for d in days if d.weekday() == day.weekday
        )
    weeks: dict[date, int] = {}
    for d in days:
        monday = d - timedelta(d.weekday())
        weeks[monday] = weeks.get(monday, 0) + 1
    per_week = tree.program.days_per_week
    sessions_count = sum(min(per_week, covered) for covered in weeks.values())
    mean_sets = sum(sets_of.values()) / len(sets_of) if sets_of else 0
    return sessions_count, round(sessions_count * mean_sets)


async def adherence(session: AsyncSession, scope: Scope, window: Window) -> Adherence | None:
    """None without an active program, or when it starts after the window."""
    programs = ProgramRepository(session, scope.user_id)
    active = await programs.active()
    if active is None:
        return None
    tree = await programs.tree(active.id)
    created = active.created_at.astimezone(scope.zone).date()
    if tree is None or created > window.end:
        return None
    covered = Window(max(window.start, created), window.end)
    planned_sessions, planned_sets = planned(tree, covered)
    done_sessions, done_sets = await workout_counts(
        session, scope, covered, [day.id for day, _ in tree.days]
    )
    return Adherence(
        active.id, active.name, planned_sessions, done_sessions, planned_sets, done_sets
    )
