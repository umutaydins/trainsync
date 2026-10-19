"""Rule-based program generator (ADR 0018). Deterministic: the same input and library always
give the same program; no LLM.

A template is a list of days; a day is a list of slots (movement pattern, variant, role).
Each slot takes an exercise of that pattern that the available equipment allows (bodyweight is
always available), compounds preferring free weights and accessories preferring dumbbells and
cables. `variant` picks the 2nd, 3rd… candidate so A/B days differ. Sets, reps and rest follow
the goal; accessories, then compound sets, then compounds are trimmed until the day fits the
session length.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from trainsync.modules.training.generator_templates import (
    DEFAULT_TEMPLATE,
    TEMPLATE_DAYS,
    TEMPLATE_NAMES,
    TEMPLATES,
    Role,
    Slot,
    Template,
)
from trainsync.modules.training.models import Equipment, MovementPattern, ProgramGoal

__all__ = [
    "DEFAULT_WEEKS",
    "DOSES",
    "MAX_EXERCISES_PER_DAY",
    "MIN_SESSION_MINUTES",
    "TEMPLATE_DAYS",
    "Day",
    "Dose",
    "GeneratorError",
    "LibraryExercise",
    "PlannedExercise",
    "Program",
    "Request",
    "Role",
    "Template",
    "fit",
    "generate",
    "resolve_template",
]

SETUP_SECONDS = 60  # walk over, set up, first warm-up
WORK_SECONDS = 45  # one working set
MIN_SESSION_MINUTES = 20
MAX_EXERCISES_PER_DAY = 8
DEFAULT_WEEKS = 8
SECONDS_PER_MINUTE = 60
# fit(): compound sets are first cut down to this, then (after dropping compounds) to 1.
COMPOUND_SET_FLOOR = 3
MIN_SETS = 1


_COMPOUND_EQUIPMENT = (
    Equipment.BARBELL,
    Equipment.DUMBBELL,
    Equipment.MACHINE,
    Equipment.KETTLEBELL,
    Equipment.CABLE,
    Equipment.BODYWEIGHT,
    Equipment.BAND,
)
_ACCESSORY_EQUIPMENT = (
    Equipment.DUMBBELL,
    Equipment.CABLE,
    Equipment.MACHINE,
    Equipment.BARBELL,
    Equipment.KETTLEBELL,
    Equipment.BODYWEIGHT,
    Equipment.BAND,
)


@dataclass(frozen=True, slots=True)
class Dose:
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int


# (first compound, other compounds, accessories) per goal.
DOSES: dict[ProgramGoal, tuple[Dose, Dose, Dose]] = {
    ProgramGoal.STRENGTH: (Dose(5, 3, 6, 180), Dose(4, 3, 6, 180), Dose(3, 6, 10, 90)),
    ProgramGoal.HYPERTROPHY: (Dose(4, 8, 12, 90), Dose(3, 8, 12, 90), Dose(3, 10, 15, 60)),
    ProgramGoal.GENERAL: (Dose(3, 8, 12, 75), Dose(3, 8, 12, 75), Dose(3, 10, 15, 60)),
}


@dataclass(frozen=True, slots=True)
class LibraryExercise:
    id: int
    slug: str
    name: str
    equipment: Equipment
    movement_pattern: MovementPattern


@dataclass(frozen=True, slots=True)
class Request:
    days_per_week: int
    goal: ProgramGoal
    equipment: frozenset[Equipment]
    session_minutes: int
    template: Template | None = None
    weeks: int = DEFAULT_WEEKS


@dataclass(frozen=True, slots=True)
class PlannedExercise:
    exercise: LibraryExercise
    role: Role
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int

    @property
    def seconds(self) -> int:
        return SETUP_SECONDS + self.sets * WORK_SECONDS + (self.sets - 1) * self.rest_seconds


@dataclass(frozen=True, slots=True)
class Day:
    name: str
    exercises: tuple[PlannedExercise, ...]

    @property
    def minutes(self) -> Decimal:
        return Decimal(sum(e.seconds for e in self.exercises)) / SECONDS_PER_MINUTE


@dataclass(frozen=True, slots=True)
class Program:
    name: str
    template: Template
    goal: ProgramGoal
    weeks: int
    days: tuple[Day, ...]


class GeneratorError(ValueError):
    """The request cannot produce a program (unsupported days for the template, too short)."""


def resolve_template(days_per_week: int, template: Template | None) -> Template:
    if template is None:
        if days_per_week not in DEFAULT_TEMPLATE:
            raise GeneratorError(f"no template for {days_per_week} days a week; use 2, 3, 4 or 6")
        return DEFAULT_TEMPLATE[days_per_week]
    if days_per_week not in TEMPLATE_DAYS[template]:
        allowed = " or ".join(str(d) for d in TEMPLATE_DAYS[template])
        raise GeneratorError(f"{template.value} takes {allowed} days a week")
    return template


def _candidates(
    library: Sequence[LibraryExercise], available: Collection[Equipment]
) -> dict[tuple[MovementPattern, Role], list[LibraryExercise]]:
    result: dict[tuple[MovementPattern, Role], list[LibraryExercise]] = {}
    for role, order in (
        (Role.COMPOUND, _COMPOUND_EQUIPMENT),
        (Role.ACCESSORY, _ACCESSORY_EQUIPMENT),
    ):
        rank = {equipment: index for index, equipment in enumerate(order)}
        for pattern in MovementPattern:
            result[(pattern, role)] = sorted(
                (e for e in library if e.movement_pattern == pattern and e.equipment in available),
                key=lambda e: (rank[e.equipment], e.id),
            )
    return result


def _pick(options: list[LibraryExercise], variant: int, used: set[int]) -> LibraryExercise | None:
    for offset in range(len(options)):
        option = options[(variant + offset) % len(options)]
        if option.id not in used:
            return option
    return None


def _dose(goal: ProgramGoal, role: Role, first_compound: bool) -> Dose:
    first, other, accessory = DOSES[goal]
    if role is Role.ACCESSORY:
        return accessory
    return first if first_compound else other


def _build_day(
    name: str,
    slots: Sequence[Slot],
    goal: ProgramGoal,
    candidates: dict[tuple[MovementPattern, Role], list[LibraryExercise]],
) -> list[PlannedExercise]:
    used: set[int] = set()
    planned: list[PlannedExercise] = []
    for slot in slots:
        exercise = _pick(candidates[(slot.pattern, slot.role)], slot.variant, used)
        if exercise is None:
            continue
        used.add(exercise.id)
        first = slot.role is Role.COMPOUND and not any(p.role is Role.COMPOUND for p in planned)
        dose = _dose(goal, slot.role, first)
        planned.append(
            PlannedExercise(
                exercise, slot.role, dose.sets, dose.rep_min, dose.rep_max, dose.rest_seconds
            )
        )
    if not planned:
        raise GeneratorError(f"no exercise in the library fits {name} with this equipment")
    return planned[:MAX_EXERCISES_PER_DAY]


def _seconds(exercises: Sequence[PlannedExercise]) -> int:
    return sum(e.seconds for e in exercises)


def fit(exercises: Sequence[PlannedExercise], minutes: int) -> list[PlannedExercise]:
    """Trim to the budget: drop accessories (last first), cut compound sets to 3, drop
    compounds (last first, keeping one), then cut the remaining sets down to 1."""
    budget = minutes * SECONDS_PER_MINUTE
    day = list(exercises)
    while _seconds(day) > budget and any(e.role is Role.ACCESSORY for e in day):
        last = max(i for i, e in enumerate(day) if e.role is Role.ACCESSORY)
        del day[last]
    for floor in (COMPOUND_SET_FLOOR, MIN_SETS):
        for index in reversed(range(len(day))):
            while _seconds(day) > budget and day[index].sets > floor:
                day[index] = replace(day[index], sets=day[index].sets - 1)
        while floor == COMPOUND_SET_FLOOR and _seconds(day) > budget and len(day) > 1:
            day.pop()
    return day


def generate(request: Request, library: Sequence[LibraryExercise]) -> Program:
    if request.session_minutes < MIN_SESSION_MINUTES:
        raise GeneratorError(f"sessions need at least {MIN_SESSION_MINUTES} minutes")
    template = resolve_template(request.days_per_week, request.template)
    available = {*request.equipment, Equipment.BODYWEIGHT}
    candidates = _candidates(library, available)
    days = tuple(
        Day(
            name,
            tuple(fit(_build_day(name, slots, request.goal, candidates), request.session_minutes)),
        )
        for name, slots in TEMPLATES[template][: request.days_per_week]
    )
    name = (
        f"{TEMPLATE_NAMES[template]} {request.goal.value} "
        f"({request.days_per_week} days, {request.session_minutes} min)"
    )
    return Program(name, template, request.goal, request.weeks, days)
