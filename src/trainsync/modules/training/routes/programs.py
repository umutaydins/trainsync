"""`/v1/training/programs`: training programs with their days and planned exercises."""

from datetime import datetime, time
from typing import Annotated, Any, Self

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.deps import SessionmakerDep, require_api_key
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.training.models import (
    Exercise,
    Program,
    ProgramDay,
    ProgramExercise,
    ProgramGoal,
)
from trainsync.modules.training.models import Progression as ProgressionKind
from trainsync.modules.training.repository import ExerciseRepository, ProgramRepository, ProgramTree
from trainsync.modules.training.schemas import EXERCISE_EXAMPLE, ExerciseOut, Kg, WeightIn

router = APIRouter(
    prefix="/v1/training", tags=["training"], dependencies=[Depends(require_api_key)]
)

NOT_FOUND = error("Unknown program", "program not found")
UNKNOWN_EXERCISE = error("A planned exercise does not exist", "unknown exercise ids: [999]")

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
    sets: int = Field(ge=1, le=10)
    rep_min: int = Field(ge=1, le=100)
    rep_max: int = Field(ge=1, le=100)
    rest_seconds: int = Field(ge=0, le=900)
    start_weight_kg: WeightIn | None = None
    progression: ProgressionKind = ProgressionKind.DOUBLE

    @model_validator(mode="after")
    def _rep_range(self) -> Self:
        if self.rep_max < self.rep_min:
            raise ValueError("rep_max must be ≥ rep_min")
        return self


class ProgramDayIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exercises: list[PlannedExerciseIn] = Field(max_length=20)
    weekday: int | None = Field(
        default=None,
        ge=0,
        le=6,
        description="0 = Monday. Null: the default spread by days per week (ADR 0030)",
    )
    start_time: time | None = Field(
        default=None, description="Local start time (CHECKIN_TZ). Null: WORKOUT_REMINDER_TIME"
    )


class ProgramIn(BaseModel):
    """`days_per_week` is the number of days."""

    model_config = ConfigDict(json_schema_extra={"examples": [PROGRAM_IN_EXAMPLE]})

    name: str = Field(min_length=1, max_length=80)
    goal: ProgramGoal
    weeks: int = Field(default=8, ge=1, le=52)
    days: list[ProgramDayIn] = Field(min_length=1, max_length=7)


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


async def load_program(session: AsyncSession, program_id: int) -> ProgramOut:
    tree = await ProgramRepository(session).tree(program_id)
    if tree is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
    return await program_out(session, tree)


async def program_out(session: AsyncSession, tree: ProgramTree) -> ProgramOut:
    ids = sorted({e.exercise_id for _, planned in tree.days for e in planned})
    exercises = await ExerciseRepository(session).by_ids(ids)
    await session.flush()
    await session.refresh(tree.program)  # `activate` updates in bulk
    summary = ProgramSummary.from_row(tree.program)
    return ProgramOut(
        **summary.model_dump(),
        days=[
            ProgramDayOut(
                id=day.id,
                day_index=day.day_index,
                name=day.name,
                weekday=day.weekday,
                start_time=day.start_time,
                exercises=[
                    PlannedExerciseOut.from_row(p, exercises[p.exercise_id]) for p in planned
                ],
            )
            for day, planned in tree.days
        ],
    )


async def _rows(
    session: AsyncSession, body: ProgramIn
) -> list[tuple[ProgramDay, list[ProgramExercise]]]:
    wanted = {e.exercise_id for day in body.days for e in day.exercises}
    known = await ExerciseRepository(session).by_ids(sorted(wanted))
    missing = sorted(wanted - known.keys())
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown exercise ids: {missing}")
    return [
        (
            ProgramDay(
                day_index=index, name=day.name, weekday=day.weekday, start_time=day.start_time
            ),
            [
                ProgramExercise(
                    exercise_id=e.exercise_id,
                    sets=e.sets,
                    rep_min=e.rep_min,
                    rep_max=e.rep_max,
                    rest_seconds=e.rest_seconds,
                    start_weight_kg=e.start_weight_kg,
                    progression=e.progression,
                )
                for e in day.exercises
            ],
        )
        for index, day in enumerate(body.days)
    ]


@router.get(
    "/programs",
    summary="List programs",
    description="Every program, newest first, without days.",
    response_model=ProgramList,
    responses={**UNAUTHORIZED},
)
async def list_programs(sessionmaker: SessionmakerDep) -> ProgramList:
    async with sessionmaker() as session:
        rows = await ProgramRepository(session).all()
    return ProgramList(items=[ProgramSummary.from_row(r) for r in rows])


@router.post(
    "/programs",
    summary="Create a program",
    description=(
        "A program with its days (in order) and planned exercises (in order). The program "
        "generator's preview (`POST /programs/generate`) has a `program` field that can be sent "
        "here unchanged. New programs are inactive."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 400: UNKNOWN_EXERCISE},
)
async def create_program(sessionmaker: SessionmakerDep, body: ProgramIn) -> ProgramOut:
    async with sessionmaker.begin() as session:
        days = await _rows(session, body)
        program = await ProgramRepository(session).add(
            Program(name=body.name, goal=body.goal, days_per_week=len(days), weeks=body.weeks),
            days,
        )
        return await load_program(session, program.id)


@router.get(
    "/programs/active",
    summary="Get the active program",
    description="The one active program with its days, or `404` when none is active.",
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 404: error("No active program", "no active program")},
)
async def get_active_program(sessionmaker: SessionmakerDep) -> ProgramOut:
    async with sessionmaker() as session:
        program = await ProgramRepository(session).active()
        if program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no active program")
        return await load_program(session, program.id)


@router.get(
    "/programs/{program_id}",
    summary="Get a program",
    description="One program with its days and planned exercises.",
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def get_program(
    sessionmaker: SessionmakerDep, program_id: Annotated[int, Path(examples=[3])]
) -> ProgramOut:
    async with sessionmaker() as session:
        return await load_program(session, program_id)


@router.put(
    "/programs/{program_id}",
    summary="Replace a program",
    description=(
        "Replaces name, goal, weeks and all days. Logged workouts stay; their link to a "
        "replaced program day becomes null."
    ),
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 400: UNKNOWN_EXERCISE, 404: NOT_FOUND},
)
async def replace_program(
    sessionmaker: SessionmakerDep,
    program_id: Annotated[int, Path(examples=[3])],
    body: ProgramIn,
) -> ProgramOut:
    async with sessionmaker.begin() as session:
        repo = ProgramRepository(session)
        program = await repo.get(program_id)
        if program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
        days = await _rows(session, body)
        program.name, program.goal, program.weeks = body.name, body.goal, body.weeks
        program.days_per_week = len(days)
        await repo.replace_days(program_id, days)
        return await load_program(session, program_id)


@router.delete(
    "/programs/{program_id}",
    summary="Delete a program",
    description="Deletes the program and its days; logged workouts stay.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def delete_program(
    sessionmaker: SessionmakerDep, program_id: Annotated[int, Path(examples=[3])]
) -> Response:
    async with sessionmaker.begin() as session:
        if not await ProgramRepository(session).delete(program_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/programs/{program_id}/activate",
    summary="Activate a program",
    description="Makes this the only active program (idempotent).",
    response_model=ProgramOut,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def activate_program(
    sessionmaker: SessionmakerDep, program_id: Annotated[int, Path(examples=[3])]
) -> ProgramOut:
    async with sessionmaker.begin() as session:
        repo = ProgramRepository(session)
        if await repo.get(program_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
        await repo.activate(program_id)
        return await load_program(session, program_id)
