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
from enum import StrEnum

from trainsync.db.models import Equipment, MovementPattern, ProgramGoal

P = MovementPattern

SETUP_SECONDS = 60  # walk over, set up, first warm-up
WORK_SECONDS = 45  # one working set
MIN_SESSION_MINUTES = 20
MAX_EXERCISES_PER_DAY = 8
DEFAULT_WEEKS = 8


class Template(StrEnum):
    FULL_BODY = "full_body"
    UPPER_LOWER = "upper_lower"
    PUSH_PULL_LEGS = "push_pull_legs"


class Role(StrEnum):
    COMPOUND = "compound"
    ACCESSORY = "accessory"


TEMPLATE_DAYS: dict[Template, tuple[int, ...]] = {
    Template.FULL_BODY: (2, 3),
    Template.UPPER_LOWER: (4,),
    Template.PUSH_PULL_LEGS: (3, 6),
}
DEFAULT_TEMPLATE: dict[int, Template] = {
    2: Template.FULL_BODY,
    3: Template.FULL_BODY,
    4: Template.UPPER_LOWER,
    6: Template.PUSH_PULL_LEGS,
}
TEMPLATE_NAMES = {
    Template.FULL_BODY: "Full Body",
    Template.UPPER_LOWER: "Upper/Lower",
    Template.PUSH_PULL_LEGS: "Push/Pull/Legs",
}

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
        return Decimal(sum(e.seconds for e in self.exercises)) / 60


@dataclass(frozen=True, slots=True)
class Program:
    name: str
    template: Template
    goal: ProgramGoal
    weeks: int
    days: tuple[Day, ...]


class GeneratorError(ValueError):
    """The request cannot produce a program (unsupported days for the template, too short)."""


@dataclass(frozen=True, slots=True)
class Slot:
    pattern: MovementPattern
    role: Role
    variant: int = 0


def _c(pattern: MovementPattern, variant: int = 0) -> Slot:
    return Slot(pattern, Role.COMPOUND, variant)


def _a(pattern: MovementPattern, variant: int = 0) -> Slot:
    return Slot(pattern, Role.ACCESSORY, variant)


def _push(v: int) -> list[Slot]:
    return [
        _c(P.HORIZONTAL_PUSH, v),
        _c(P.VERTICAL_PUSH, v),
        _c(P.HORIZONTAL_PUSH, v + 1),
        _a(P.CHEST_FLY, v),
        _a(P.LATERAL_RAISE, v),
        _a(P.TRICEPS, v),
    ]


def _pull(v: int) -> list[Slot]:
    return [
        _c(P.VERTICAL_PULL, v),
        _c(P.HORIZONTAL_PULL, v),
        _c(P.HORIZONTAL_PULL, v + 1),
        _a(P.REAR_DELT, v),
        _a(P.BICEPS, v),
        _a(P.BICEPS, v + 1),
    ]


def _legs(v: int) -> list[Slot]:
    return [
        _c(P.SQUAT, v),
        _c(P.HINGE, v),
        _c(P.LUNGE, v),
        _a(P.KNEE_EXTENSION, v),
        _a(P.KNEE_FLEXION, v),
        _a(P.CALF_RAISE, v),
        _a(P.CORE, v),
    ]


FULL_BODY_DAYS: list[tuple[str, list[Slot]]] = [
    (
        "Full Body A",
        [
            _c(P.SQUAT),
            _c(P.HORIZONTAL_PUSH),
            _c(P.HORIZONTAL_PULL),
            _a(P.LATERAL_RAISE),
            _a(P.BICEPS),
            _a(P.CORE),
        ],
    ),
    (
        "Full Body B",
        [
            _c(P.HINGE),
            _c(P.VERTICAL_PUSH),
            _c(P.VERTICAL_PULL),
            _c(P.LUNGE),
            _a(P.TRICEPS),
            _a(P.REAR_DELT),
            _a(P.CALF_RAISE),
        ],
    ),
    (
        "Full Body C",
        [
            _c(P.SQUAT, 1),
            _c(P.HORIZONTAL_PUSH, 1),
            _c(P.VERTICAL_PULL, 1),
            _c(P.HINGE, 1),
            _a(P.CHEST_FLY),
            _a(P.KNEE_FLEXION),
            _a(P.BICEPS, 1),
            _a(P.CORE, 1),
        ],
    ),
]
UPPER_LOWER_DAYS: list[tuple[str, list[Slot]]] = [
    (
        "Upper A",
        [
            _c(P.HORIZONTAL_PUSH),
            _c(P.HORIZONTAL_PULL),
            _c(P.VERTICAL_PUSH),
            _c(P.VERTICAL_PULL),
            _a(P.LATERAL_RAISE),
            _a(P.BICEPS),
            _a(P.TRICEPS),
        ],
    ),
    (
        "Lower A",
        [
            _c(P.SQUAT),
            _c(P.HINGE, 1),
            _c(P.LUNGE),
            _a(P.KNEE_FLEXION),
            _a(P.CALF_RAISE),
            _a(P.CORE),
        ],
    ),
    (
        "Upper B",
        [
            _c(P.VERTICAL_PUSH, 1),
            _c(P.VERTICAL_PULL, 1),
            _c(P.HORIZONTAL_PUSH, 1),
            _c(P.HORIZONTAL_PULL, 1),
            _a(P.CHEST_FLY),
            _a(P.REAR_DELT),
            _a(P.BICEPS, 1),
            _a(P.TRICEPS, 1),
        ],
    ),
    (
        "Lower B",
        [
            _c(P.HINGE),
            _c(P.SQUAT, 1),
            _c(P.LUNGE, 1),
            _a(P.KNEE_EXTENSION),
            _a(P.KNEE_FLEXION),
            _a(P.CALF_RAISE),
            _a(P.CORE, 1),
        ],
    ),
]
PPL_DAYS: list[tuple[str, list[Slot]]] = [
    ("Push A", _push(0)),
    ("Pull A", _pull(0)),
    ("Legs A", _legs(0)),
    ("Push B", _push(1)),
    ("Pull B", _pull(1)),
    ("Legs B", _legs(1)),
]
TEMPLATES: dict[Template, list[tuple[str, list[Slot]]]] = {
    Template.FULL_BODY: FULL_BODY_DAYS,
    Template.UPPER_LOWER: UPPER_LOWER_DAYS,
    Template.PUSH_PULL_LEGS: PPL_DAYS,
}


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
    budget = minutes * 60
    day = list(exercises)
    while _seconds(day) > budget and any(e.role is Role.ACCESSORY for e in day):
        last = max(i for i, e in enumerate(day) if e.role is Role.ACCESSORY)
        del day[last]
    for floor in (3, 1):
        for index in reversed(range(len(day))):
            while _seconds(day) > budget and day[index].sets > floor:
                day[index] = replace(day[index], sets=day[index].sets - 1)
        while floor == 3 and _seconds(day) > budget and len(day) > 1:
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
