"""Underperformance, measured (ADR 0030): a set below the plan, planned sets missing, and the
verdict of a finished workout. Pure functions over the API's own `WorkoutDetail`, so the coach
judges exactly what the web shows."""

from dataclasses import dataclass
from decimal import Decimal

from trainsync.modules.training.schemas import SetOut
from trainsync.modules.training.workout_schemas import PlannedExercise, WorkoutDetail


def target_weight(planned: PlannedExercise) -> Decimal | None:
    """The suggested weight for this session, else the planned start weight (None = no target)."""
    return planned.suggestion.weight_kg or planned.start_weight_kg


def is_under_target(planned: PlannedExercise, logged: SetOut) -> bool:
    """A working set with fewer reps than `rep_min`, or lighter than the session's target weight.
    Bodyweight work (no target weight) is judged on reps only."""
    if logged.is_warmup:
        return False
    target = target_weight(planned)
    if target is not None and target > 0 and logged.weight_kg < target:
        return True
    return logged.reps < planned.rep_min


@dataclass(frozen=True, slots=True)
class Verdict:
    good: bool
    missing_sets: int
    under_target: tuple[SetOut, ...]
    pr_count: int


def planned_for(detail: WorkoutDetail, exercise_id: int) -> PlannedExercise | None:
    return next((p for p in detail.planned if p.exercise.id == exercise_id), None)


def missing_sets(detail: WorkoutDetail) -> int:
    """Planned working sets that were not logged, summed over the planned exercises."""
    missing = 0
    for planned in detail.planned:
        done = sum(
            1 for s in detail.sets if s.exercise_id == planned.exercise.id and not s.is_warmup
        )
        missing += max(0, planned.sets - done)
    return missing


def verdict(detail: WorkoutDetail) -> Verdict:
    under = tuple(
        s
        for s in detail.sets
        if (planned := planned_for(detail, s.exercise_id)) and is_under_target(planned, s)
    )
    missing = missing_sets(detail)
    return Verdict(
        good=missing == 0 and not under,
        missing_sets=missing,
        under_target=under,
        pr_count=len(detail.records),
    )
