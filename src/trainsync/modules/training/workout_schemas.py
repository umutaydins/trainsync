"""Workout and set schemas of `/v1/training/workouts` (also the bot's and coach's types)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trainsync.modules.training.models import Progression as ProgressionKind
from trainsync.modules.training.progression import Action, Suggestion
from trainsync.modules.training.schemas import (
    EXERCISE_EXAMPLE,
    PR_EXAMPLE,
    SET_EXAMPLE,
    ExerciseOut,
    Kg,
    RecordOut,
    RpeIn,
    SetOut,
    WeightIn,
)

MAX_NOTES_LENGTH = 2000
MAX_SET_INDEX = 100
MAX_REPS = 100
MAX_REST_SECONDS = 24 * 60 * 60

LAST_EXAMPLE: dict[str, Any] = {
    "workout_id": 41,
    "started_at": "2026-10-15T17:30:00Z",
    "sets": [{"reps": 10, "weight_kg": 77.5, "rpe": 8.5}, {"reps": 9, "weight_kg": 77.5}],
}
PLANNED_EXAMPLE: dict[str, Any] = {
    "exercise": EXERCISE_EXAMPLE,
    "sets": 3,
    "rep_min": 8,
    "rep_max": 12,
    "rest_seconds": 90,
    "start_weight_kg": 60.0,
    "progression": "double",
    "last_performance": LAST_EXAMPLE,
    "suggestion": {"action": "hold", "weight_kg": 77.5, "previous_weight_kg": 77.5},
}
SUMMARY_EXAMPLE: dict[str, Any] = {
    "client_id": "2d7f6c0a-5b1e-4c3a-8f0e-9a4b1c2d3e4f",
    "id": 42,
    "program_day_id": 11,
    "program_day_name": "Upper A",
    "started_at": "2026-10-18T17:30:00Z",
    "ended_at": "2026-10-18T18:35:00Z",
    "notes": "",
    "set_count": 14,
    "exercise_count": 5,
    "volume_kg": 8240.0,
}
DETAIL_EXAMPLE: dict[str, Any] = {
    **SUMMARY_EXAMPLE,
    "planned": [PLANNED_EXAMPLE],
    "sets": [SET_EXAMPLE],
    "records": [PR_EXAMPLE],
}
SET_IN_EXAMPLE: dict[str, Any] = {
    key: SET_EXAMPLE[key]
    for key in (
        "exercise_id",
        "set_index",
        "reps",
        "weight_kg",
        "rpe",
        "is_warmup",
        "completed_at",
        "rest_seconds",
    )
}


class PerformedSet(BaseModel):
    reps: int
    weight_kg: Kg
    rpe: Kg | None = None


class LastPerformance(BaseModel):
    """Working sets of the most recent other workout that logged the exercise."""

    workout_id: int
    started_at: datetime
    sets: list[PerformedSet]


class SuggestionOut(BaseModel):
    """Next weight by double progression (ADR 0018). `start`: no history yet, `weight_kg` is
    the planned start weight (may be null); `increase`: every set hit `rep_max` last time;
    `deload`: two sessions in a row below `rep_min` (-10 %); `hold`: same weight, more reps."""

    action: Action
    weight_kg: Kg | None
    previous_weight_kg: Kg | None = Field(description="Working weight of the last session")

    @classmethod
    def from_suggestion(cls, suggestion: Suggestion) -> "SuggestionOut":
        return cls(
            action=suggestion.action,
            weight_kg=suggestion.weight_kg,
            previous_weight_kg=suggestion.previous_weight_kg,
        )


class PlannedExercise(BaseModel):
    """A program-day exercise with what was lifted last time."""

    model_config = ConfigDict(json_schema_extra={"examples": [PLANNED_EXAMPLE]})

    exercise: ExerciseOut
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int
    start_weight_kg: Kg | None
    progression: ProgressionKind
    last_performance: LastPerformance | None
    suggestion: SuggestionOut


class WorkoutSummary(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [SUMMARY_EXAMPLE]})

    id: int
    client_id: uuid.UUID = Field(description="The id the client started it with (ADR 0017)")
    program_day_id: int | None
    program_day_name: str | None
    started_at: datetime
    ended_at: datetime | None = Field(description="null while the workout is in progress")
    notes: str
    set_count: int = Field(description="Logged sets, warm-ups included")
    exercise_count: int
    volume_kg: Kg = Field(description="Sum of reps x weight of the working sets")


class WorkoutDetail(WorkoutSummary):
    model_config = ConfigDict(json_schema_extra={"examples": [DETAIL_EXAMPLE]})

    planned: list[PlannedExercise] = Field(
        description="The program day's exercises in order; empty for a free workout"
    )
    sets: list[SetOut] = Field(description="In completion order")
    records: list[RecordOut] = Field(
        description="Personal records these sets beat, against every earlier workout"
    )


class WorkoutPage(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [SUMMARY_EXAMPLE], "next_cursor": None}]}
    )

    items: list[WorkoutSummary]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page")


class WorkoutStart(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"program_day_id": 11}, {"notes": "hotel gym"}]}
    )

    program_day_id: int | None = Field(default=None, description="Plan to follow, if any")
    started_at: datetime | None = Field(default=None, description="Default: now")
    notes: str = Field(default="", max_length=MAX_NOTES_LENGTH)


class WorkoutFinish(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"ended_at": "2026-10-18T18:35:00Z", "notes": "good"}]}
    )

    ended_at: datetime | None = Field(default=None, description="Default: now")
    notes: str | None = Field(default=None, max_length=MAX_NOTES_LENGTH)


class SetIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [SET_IN_EXAMPLE]})

    exercise_id: int
    set_index: int = Field(
        ge=0, le=MAX_SET_INDEX, description="Order of the set within the exercise"
    )
    reps: int = Field(ge=0, le=MAX_REPS)
    weight_kg: WeightIn
    rpe: RpeIn | None = None
    is_warmup: bool = False
    completed_at: datetime = Field(
        description="When the set was done, as the client saw it (part of the idempotent body)"
    )
    rest_seconds: int | None = Field(default=None, ge=0, le=MAX_REST_SECONDS)
