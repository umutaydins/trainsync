"""Program schemas of `/v1/training/programs`: what a program is created with and read as."""

from datetime import datetime, time
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trainsync.modules.training.models import Exercise, Program, ProgramExercise, ProgramGoal
from trainsync.modules.training.models import Progression as ProgressionKind
from trainsync.modules.training.schemas import EXERCISE_EXAMPLE, ExerciseOut, Kg, WeightIn

MAX_SETS = 10
MAX_REPS = 100
MAX_REST_SECONDS = 15 * 60
MAX_NAME_LENGTH = 80
MAX_EXERCISES_PER_DAY = 20
MONDAY, SUNDAY = 0, 6
DAYS_PER_WEEK = 7
DEFAULT_WEEKS = 8
MAX_WEEKS = 52

PLANNED_IN_EXAMPLE: dict[str, Any] = {
    "exercise_id": 20,
    "sets": 3,
    "rep_min": 8,
    "rep_max": 12,
    "rest_seconds": 90,
    "start_weight_kg": 60.0,
    "progression": "double",
}
PROGRAM_IN_EXAMPLE: dict[str, Any] = {
    "name": "Upper/Lower",
    "goal": "hypertrophy",
    "weeks": 8,
    "days": [
        {"name": "Upper A", "exercises": [PLANNED_IN_EXAMPLE]},
        {"name": "Lower A", "exercises": [{**PLANNED_IN_EXAMPLE, "exercise_id": 1}]},
    ],
}


class PlannedExerciseIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PLANNED_IN_EXAMPLE]})

    exercise_id: int
    sets: int = Field(ge=1, le=MAX_SETS)
    rep_min: int = Field(ge=1, le=MAX_REPS)
    rep_max: int = Field(ge=1, le=MAX_REPS)
    rest_seconds: int = Field(ge=0, le=MAX_REST_SECONDS)
    start_weight_kg: WeightIn | None = None
    progression: ProgressionKind = ProgressionKind.DOUBLE

    @model_validator(mode="after")
    def _rep_range(self) -> Self:
        if self.rep_max < self.rep_min:
            raise ValueError("rep_max must be ≥ rep_min")
        return self


class ProgramDayIn(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    exercises: list[PlannedExerciseIn] = Field(max_length=MAX_EXERCISES_PER_DAY)
    weekday: int | None = Field(
        default=None,
        ge=MONDAY,
        le=SUNDAY,
        description="0 = Monday. Null: the default spread by days per week (ADR 0030)",
    )
    start_time: time | None = Field(
        default=None, description="Local start time (CHECKIN_TZ). Null: WORKOUT_REMINDER_TIME"
    )


class ProgramIn(BaseModel):
    """`days_per_week` is the number of days."""

    model_config = ConfigDict(json_schema_extra={"examples": [PROGRAM_IN_EXAMPLE]})

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    goal: ProgramGoal
    weeks: int = Field(default=DEFAULT_WEEKS, ge=1, le=MAX_WEEKS)
    days: list[ProgramDayIn] = Field(min_length=1, max_length=DAYS_PER_WEEK)


PLANNED_EXAMPLE: dict[str, Any] = {
    "id": 7,
    "position": 0,
    "exercise": EXERCISE_EXAMPLE,
    "sets": 3,
    "rep_min": 8,
    "rep_max": 12,
    "rest_seconds": 90,
    "start_weight_kg": 60.0,
    "progression": "double",
}
PROGRAM_SUMMARY_EXAMPLE: dict[str, Any] = {
    "id": 3,
    "name": "Upper/Lower",
    "goal": "hypertrophy",
    "days_per_week": 4,
    "weeks": 8,
    "active": True,
    "created_at": "2026-10-18T10:00:00Z",
}
PROGRAM_EXAMPLE: dict[str, Any] = {
    **PROGRAM_SUMMARY_EXAMPLE,
    "days": [
        {
            "id": 11,
            "day_index": 0,
            "name": "Upper A",
            "weekday": 0,
            "start_time": "18:00:00",
            "exercises": [PLANNED_EXAMPLE],
        }
    ],
}


class PlannedExerciseOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PLANNED_EXAMPLE]})

    id: int
    position: int
    exercise: ExerciseOut
    sets: int
    rep_min: int
    rep_max: int
    rest_seconds: int
    start_weight_kg: Kg | None
    progression: ProgressionKind

    @classmethod
    def from_row(cls, row: ProgramExercise, exercise: Exercise) -> "PlannedExerciseOut":
        return cls(
            id=row.id,
            position=row.position,
            exercise=ExerciseOut.from_row(exercise),
            sets=row.sets,
            rep_min=row.rep_min,
            rep_max=row.rep_max,
            rest_seconds=row.rest_seconds,
            start_weight_kg=row.start_weight_kg,
            progression=ProgressionKind(row.progression),
        )


class ProgramDayOut(BaseModel):
    id: int
    day_index: int
    name: str
    weekday: int | None = Field(default=None, description="0 = Monday; null = default spread")
    start_time: time | None = Field(default=None, description="Local start time; null = default")
    exercises: list[PlannedExerciseOut]


class ProgramSummary(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PROGRAM_SUMMARY_EXAMPLE]})

    id: int
    name: str
    goal: ProgramGoal
    days_per_week: int
    weeks: int
    active: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row: Program) -> "ProgramSummary":
        return cls(
            id=row.id,
            name=row.name,
            goal=ProgramGoal(row.goal),
            days_per_week=row.days_per_week,
            weeks=row.weeks,
            active=row.active,
            created_at=row.created_at,
        )


class ProgramOut(ProgramSummary):
    model_config = ConfigDict(json_schema_extra={"examples": [PROGRAM_EXAMPLE]})

    days: list[ProgramDayOut]


class ProgramList(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [PROGRAM_SUMMARY_EXAMPLE]}]}
    )

    items: list[ProgramSummary]
