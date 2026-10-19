"""Check-in state: the steps, what is kept between updates, and the deterministic ids and keys."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from trainsync.modules.chat.common import client_id
from trainsync.modules.chat.training import plan_text, suggested_load
from trainsync.modules.checkin.models import CheckinStatus
from trainsync.modules.coach.packs import Key
from trainsync.modules.training.models import Equipment
from trainsync.modules.training.workout_schemas import PlannedExercise

STATE_TTL_S = 6 * 3600
CALLBACK_PREFIX = "ci"
STATUS_CODES: dict[str, CheckinStatus] = {
    "done": CheckinStatus.DONE,
    "partial": CheckinStatus.PARTIAL,
    "skipped": CheckinStatus.SKIPPED,
    "rest": CheckinStatus.REST,
    "sick": CheckinStatus.SICK_OR_INJURED,
}
STATUS_BUTTONS: dict[CheckinStatus, Key] = {
    CheckinStatus.DONE: Key.CHECKIN_BTN_DONE,
    CheckinStatus.PARTIAL: Key.CHECKIN_BTN_PARTIAL,
    CheckinStatus.SKIPPED: Key.CHECKIN_BTN_SKIPPED,
    CheckinStatus.REST: Key.CHECKIN_BTN_REST,
    CheckinStatus.SICK_OR_INJURED: Key.CHECKIN_BTN_SICK,
}

Step = Literal["status", "exercise", "freeform", "reason", "scale", "sleep", "energy", "done"]
TEXT_STEPS: frozenset[Step] = frozenset(
    {"exercise", "freeform", "reason", "scale", "sleep", "energy"}
)
# Questions that can be skipped with the Skip button.
SKIPPABLE_STEPS: frozenset[Step] = frozenset({"reason", "scale", "sleep", "energy"})
ENERGY_LEVELS = range(1, 6)


class Planned(BaseModel):
    """What the check-in needs of one planned exercise."""

    exercise_id: int
    name: str
    sets: int
    reps: int  # "As planned" logs the bottom of the rep range (ADR 0020)
    plan: str
    suggested: str
    weight_kg: Decimal | None  # None: no suggestion, type the sets

    @classmethod
    def from_planned(cls, planned: PlannedExercise) -> "Planned":
        weight = planned.suggestion.weight_kg
        if weight is None and planned.exercise.equipment == Equipment.BODYWEIGHT:
            weight = Decimal(0)
        return cls(
            exercise_id=planned.exercise.id,
            name=planned.exercise.name,
            sets=planned.sets,
            reps=planned.rep_min,
            plan=plan_text(planned),
            suggested=suggested_load(planned),
            weight_kg=weight,
        )


class FlowState(BaseModel):
    seq: int = 0
    step: Step = "status"
    status: CheckinStatus | None = None
    workout_id: int | None = None
    planned: list[Planned] = Field(default_factory=list)
    index: int = 0
    logged: dict[int, int] = Field(default_factory=dict)  # exercise id → sets stored
    choices: list[tuple[int, str]] = Field(default_factory=list)  # freeform: which exercise?
    choice_sets: str = ""
    reason: str | None = None
    scale_kg: Decimal | None = None
    sleep_hours: Decimal | None = None
    energy: int | None = None
    last_update_id: int = 0


def workout_client_id(day: date) -> uuid.UUID:
    """The id the check-in starts the day's workout with: a retry or an edit reuses it."""
    return client_id(f"checkin:{day.isoformat()}:workout")


def set_id(day: date, exercise_id: int, set_index: int) -> uuid.UUID:
    """Deterministic client id of a check-in set: answering twice rewrites the same set."""
    return client_id(f"checkin:{day.isoformat()}:{exercise_id}:{set_index}")


def state_key(chat_id: int, day: date) -> str:
    return f"checkin:{chat_id}:{day:%Y%m%d}"


def callback(day: date, seq: int, action: str) -> str:
    return f"{CALLBACK_PREFIX}:{day:%Y%m%d}:{seq}:{action}"


def workout_id_of(state: FlowState) -> int:
    if state.workout_id is None:  # pragma: no cover - set before any set is logged
        raise RuntimeError("check-in step without a workout")
    return state.workout_id
