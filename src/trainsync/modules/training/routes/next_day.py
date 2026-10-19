"""`/v1/training/programs/active/next-day`: which program day is up, with suggested weights.

Rotation (P6.8): the days of the active program are followed in order. The day after the one
the most recent workout followed is next (after the last day, the first again); with no such
workout yet it is the first day. A workout that followed a day and is still open (no `ended_at`)
keeps that day current, with its id, so a client can continue it.
"""

from datetime import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import SessionmakerDep, SettingsDep, require_api_key
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.training.models import Workout
from trainsync.modules.training.repository import ProgramRepository, WorkoutRepository
from trainsync.modules.training.routes.workouts import (
    PLANNED_EXAMPLE,
    PlannedExercise,
    planned_exercises,
    progression_rules,
)

router = APIRouter(
    prefix="/v1/training", tags=["training"], dependencies=[Depends(require_api_key)]
)

NEXT_DAY_EXAMPLE: dict[str, Any] = {
    "program_id": 3,
    "program_name": "Upper/Lower",
    "day_id": 11,
    "day_index": 0,
    "day_name": "Upper A",
    "weekday": 0,
    "start_time": "18:00:00",
    "open_workout_id": None,
    "planned": [PLANNED_EXAMPLE],
}


class NextDay(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [NEXT_DAY_EXAMPLE]})

    program_id: int
    program_name: str
    day_id: int
    day_index: int
    day_name: str
    weekday: int | None = Field(
        default=None, description="0 = Monday; null = default spread (ADR 0030)"
    )
    start_time: time | None = Field(
        default=None, description="Local start time; null = WORKOUT_REMINDER_TIME"
    )
    open_workout_id: int | None = Field(
        description="An unfinished workout that follows this day, to continue instead of a new one"
    )
    planned: list[PlannedExercise] = Field(
        description="The day's exercises with last performance and suggested weight"
    )


@router.get(
    "/programs/active/next-day",
    summary="Next day of the active program",
    description=(
        "The program day that is up next, in rotation: the day after the one the latest workout "
        "followed (wrapping around), the first day if none, or the day of a still-open workout. "
        "Planned exercises come with the double-progression suggestion (ADR 0018). `404` when "
        "no program is active."
    ),
    response_model=NextDay,
    responses={**UNAUTHORIZED, 404: error("No active program", "no active program")},
)
async def next_day(sessionmaker: SessionmakerDep, settings: SettingsDep) -> NextDay:
    async with sessionmaker() as session:
        programs = ProgramRepository(session)
        program = await programs.active()
        tree = await programs.tree(program.id) if program is not None else None
        if tree is None or not tree.days:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no active program")
        days = [day for day, _ in tree.days]
        latest = await WorkoutRepository(session).latest_for_days([d.id for d in days])
        open_workout: Workout | None = None
        index = 0
        if latest is not None:
            position = next(i for i, d in enumerate(days) if d.id == latest.program_day_id)
            if latest.ended_at is None:
                index, open_workout = position, latest
            else:
                index = (position + 1) % len(days)
        day = days[index]
        # Not added to the session: only used to look up the plan and its history.
        workout = open_workout or Workout(program_day_id=day.id)
        planned = await planned_exercises(session, workout, progression_rules(settings))
        return NextDay(
            program_id=tree.program.id,
            program_name=tree.program.name,
            day_id=day.id,
            day_index=day.day_index,
            day_name=day.name,
            weekday=day.weekday,
            start_time=day.start_time,
            open_workout_id=open_workout.id if open_workout else None,
            planned=planned,
        )
