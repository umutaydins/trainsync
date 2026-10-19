"""Types shared by the training routers: kilogram fields, exercises, sets and records."""

import base64
import binascii
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from trainsync.modules.training.math import PersonalRecord, PrKind, SetEntry
from trainsync.modules.training.models import (
    Equipment,
    Exercise,
    MovementPattern,
    Muscle,
    WorkoutSet,
)
from trainsync.modules.training.repository import WorkoutKeyset

# Weights are exact decimals in the database and in requests; responses send JSON numbers.
Kg = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
WeightIn = Annotated[
    Decimal,
    Field(ge=0, le=500, multiple_of=Decimal("0.25"), description="kg, 0-500 in 0.25 steps"),
]
RpeIn = Annotated[
    Decimal, Field(ge=1, le=10, multiple_of=Decimal("0.5"), description="1-10 in 0.5 steps")
]

EXERCISE_EXAMPLE: dict[str, Any] = {
    "id": 20,
    "slug": "bench-press",
    "name": "Bench Press",
    "primary_muscle": "chest",
    "secondary_muscles": ["triceps", "shoulders"],
    "equipment": "barbell",
    "movement_pattern": "horizontal_push",
    "is_custom": False,
}


class ExerciseOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [EXERCISE_EXAMPLE]})

    id: int
    slug: str
    name: str
    primary_muscle: Muscle
    secondary_muscles: list[Muscle]
    equipment: Equipment
    movement_pattern: MovementPattern | None
    is_custom: bool

    @classmethod
    def from_row(cls, row: Exercise) -> "ExerciseOut":
        return cls(
            id=row.id,
            slug=row.slug,
            name=row.name,
            primary_muscle=Muscle(row.primary_muscle),
            secondary_muscles=[Muscle(m) for m in row.secondary_muscles],
            equipment=Equipment(row.equipment),
            movement_pattern=MovementPattern(row.movement_pattern)
            if row.movement_pattern
            else None,
            is_custom=row.is_custom,
        )


SET_EXAMPLE: dict[str, Any] = {
    "client_id": "6f1c2a52-8a7e-4f57-9a43-3c3b4b8f0d11",
    "workout_id": 42,
    "exercise_id": 20,
    "set_index": 1,
    "reps": 8,
    "weight_kg": 80.0,
    "rpe": 8.0,
    "is_warmup": False,
    "completed_at": "2026-10-18T17:42:10Z",
    "rest_seconds": 120,
}


class SetOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [SET_EXAMPLE]})

    client_id: uuid.UUID
    workout_id: int
    exercise_id: int
    set_index: int
    reps: int
    weight_kg: Kg
    rpe: Kg | None
    is_warmup: bool
    completed_at: datetime
    rest_seconds: int | None

    @classmethod
    def from_row(cls, row: WorkoutSet) -> "SetOut":
        return cls(
            client_id=row.client_id,
            workout_id=row.workout_id,
            exercise_id=row.exercise_id,
            set_index=row.set_index,
            reps=row.reps,
            weight_kg=row.weight_kg,
            rpe=row.rpe,
            is_warmup=row.is_warmup,
            completed_at=row.completed_at,
            rest_seconds=row.rest_seconds,
        )


PR_EXAMPLE: dict[str, Any] = {
    "exercise_id": 20,
    "exercise_name": "Bench Press",
    "kind": "weight_for_reps",
    "value": 82.5,
    "previous": 80.0,
    "reps": 8,
}


class RecordOut(BaseModel):
    """A personal record: `value` beats `previous` (null for a first-ever performance).
    `weight_for_reps`: kg lifted for `reps`; `e1rm`: estimated 1RM in kg; `session_volume`: kg."""

    model_config = ConfigDict(json_schema_extra={"examples": [PR_EXAMPLE]})

    exercise_id: int
    exercise_name: str
    kind: PrKind
    value: Kg
    previous: Kg | None
    reps: int | None

    @classmethod
    def from_record(cls, record: PersonalRecord, names: dict[int, str]) -> "RecordOut":
        return cls(
            exercise_id=record.exercise_id,
            exercise_name=names.get(record.exercise_id, ""),
            kind=record.kind,
            value=record.value,
            previous=record.previous,
            reps=record.reps,
        )


def entry(row: WorkoutSet) -> SetEntry:
    """The math's view of a stored set; sets of one workout share a session."""
    return SetEntry(
        session=row.workout_id,
        exercise_id=row.exercise_id,
        reps=row.reps,
        weight_kg=row.weight_kg,
        is_warmup=row.is_warmup,
    )


def encode_cursor(keyset: WorkoutKeyset) -> str:
    raw = json.dumps({"started_at": keyset.started_at.isoformat(), "id": keyset.id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> WorkoutKeyset:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        started_at = datetime.fromisoformat(data["started_at"])
        row_id = data["id"]
        if not isinstance(row_id, int) or started_at.tzinfo is None:
            raise ValueError("bad cursor fields")
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc
    return WorkoutKeyset(started_at, row_id)


def check_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "`to` is before `from`")
