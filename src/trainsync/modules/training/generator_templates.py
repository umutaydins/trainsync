"""Program generator templates (ADR 0018): which days a template has, and per day the slots
(movement pattern, role, variant) the generator fills from the exercise library."""

from dataclasses import dataclass
from enum import StrEnum

from trainsync.modules.training.models import MovementPattern

P = MovementPattern


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
