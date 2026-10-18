"""`/v1/training/exercises`: the exercise library (built-in, read-only) and custom exercises."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from trainsync.api.deps import SessionmakerDep, require_api_key
from trainsync.api.errors import UNAUTHORIZED, error
from trainsync.api.training.common import EXERCISE_EXAMPLE, ExerciseOut
from trainsync.db.models import Equipment, Exercise, MovementPattern, Muscle
from trainsync.db.repositories.training import ExerciseRepository

router = APIRouter(
    prefix="/v1/training", tags=["training"], dependencies=[Depends(require_api_key)]
)

NOT_FOUND = error("Unknown exercise", "exercise not found")


class ExerciseList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [EXERCISE_EXAMPLE]}]})

    items: list[ExerciseOut]


CUSTOM_EXAMPLE: dict[str, Any] = {
    "name": "Landmine Press",
    "primary_muscle": "shoulders",
    "secondary_muscles": ["chest", "triceps"],
    "equipment": "barbell",
    "movement_pattern": "vertical_push",
}


class ExerciseCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [CUSTOM_EXAMPLE]})

    name: str = Field(min_length=1, max_length=80)
    primary_muscle: Muscle
    secondary_muscles: list[Muscle] = Field(default_factory=list)
    equipment: Equipment
    movement_pattern: MovementPattern | None = None


class ExerciseUpdate(BaseModel):
    """Only the fields that are sent change; the slug stays."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Half-kneeling Landmine"}]})

    name: str | None = Field(default=None, min_length=1, max_length=80)
    primary_muscle: Muscle | None = None
    secondary_muscles: list[Muscle] | None = None
    equipment: Equipment | None = None
    movement_pattern: MovementPattern | None = None


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64] or "exercise"


@router.get(
    "/exercises",
    summary="List or search exercises",
    description=(
        "Built-in and custom exercises by name. `q` matches name or slug (case-insensitive "
        "substring), `muscle` the primary or a secondary muscle, `equipment` any of the given."
    ),
    response_model=ExerciseList,
    responses={**UNAUTHORIZED},
)
async def list_exercises(
    sessionmaker: SessionmakerDep,
    q: Annotated[str | None, Query(max_length=80, examples=["press"])] = None,
    muscle: Annotated[Muscle | None, Query()] = None,
    equipment: Annotated[list[Equipment] | None, Query()] = None,
) -> ExerciseList:
    async with sessionmaker() as session:
        rows = await ExerciseRepository(session).search(
            q=q, muscle=muscle, equipment=equipment, limit=500
        )
    return ExerciseList(items=[ExerciseOut.from_row(r) for r in rows])


@router.post(
    "/exercises",
    summary="Create a custom exercise",
    description="The slug is derived from the name; a name whose slug exists already is `409`.",
    status_code=status.HTTP_201_CREATED,
    response_model=ExerciseOut,
    responses={**UNAUTHORIZED, 409: error("Slug taken", "exercise `landmine-press` exists")},
)
async def create_exercise(sessionmaker: SessionmakerDep, body: ExerciseCreate) -> ExerciseOut:
    slug = slugify(body.name)
    try:
        async with sessionmaker.begin() as session:
            row = await ExerciseRepository(session).add(
                Exercise(
                    slug=slug,
                    name=body.name,
                    primary_muscle=body.primary_muscle,
                    secondary_muscles=list(body.secondary_muscles),
                    equipment=body.equipment,
                    movement_pattern=body.movement_pattern,
                    is_custom=True,
                )
            )
            out = ExerciseOut.from_row(row)
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"exercise `{slug}` exists") from exc
    return out


@router.patch(
    "/exercises/{exercise_id}",
    summary="Update a custom exercise",
    description="Built-in exercises are read-only (`409`).",
    response_model=ExerciseOut,
    responses={
        **UNAUTHORIZED,
        404: NOT_FOUND,
        409: error("Built-in exercise", "built-in exercises are read-only"),
    },
)
async def update_exercise(
    sessionmaker: SessionmakerDep,
    exercise_id: Annotated[int, Path(examples=[73])],
    body: ExerciseUpdate,
) -> ExerciseOut:
    async with sessionmaker.begin() as session:
        row = await ExerciseRepository(session).get(exercise_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "exercise not found")
        if not row.is_custom:
            raise HTTPException(status.HTTP_409_CONFLICT, "built-in exercises are read-only")
        changes = body.model_dump(exclude_unset=True)
        for field in ("name", "primary_muscle", "equipment"):
            if changes.get(field) is not None:
                setattr(row, field, changes[field])
        if body.secondary_muscles is not None:
            row.secondary_muscles = list(body.secondary_muscles)
        if "movement_pattern" in changes:
            row.movement_pattern = body.movement_pattern
        await session.flush()
        return ExerciseOut.from_row(row)
