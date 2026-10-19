"""`POST /v1/training/programs/generate` (rule-based preview, ADR 0018) and
`GET /v1/training/plates` (plates per side for a target weight)."""

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.core.deps import SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.training.generator import (
    DEFAULT_WEEKS,
    MIN_SESSION_MINUTES,
    GeneratorError,
    LibraryExercise,
    Request,
    Role,
    Template,
    generate,
)
from trainsync.modules.training.models import Equipment, MovementPattern, ProgramGoal
from trainsync.modules.training.plates import plates_per_side
from trainsync.modules.training.repository import ExerciseRepository
from trainsync.modules.training.routes.programs import (
    PROGRAM_IN_EXAMPLE,
    PlannedExerciseIn,
    ProgramDayIn,
    ProgramIn,
)
from trainsync.modules.training.schemas import Kg

router = APIRouter(prefix="/v1/training", tags=["training"])

GENERATE_EXAMPLE: dict[str, Any] = {
    "days_per_week": 4,
    "goal": "hypertrophy",
    "equipment": ["barbell", "dumbbell"],
    "session_minutes": 60,
}


class GenerateIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [GENERATE_EXAMPLE]})

    days_per_week: int = Field(
        ge=1, le=7, description="2 or 3 full body, 4 upper/lower, 3 or 6 PPL"
    )
    goal: ProgramGoal
    equipment: list[Equipment] = Field(
        default_factory=list, description="Available equipment; bodyweight is always included"
    )
    session_minutes: int = Field(default=60, ge=MIN_SESSION_MINUTES, le=180)
    template: Template | None = Field(default=None, description="Default: by days per week")
    weeks: int = Field(default=DEFAULT_WEEKS, ge=1, le=52)


PREVIEW_EXAMPLE: dict[str, Any] = {
    "template": "upper_lower",
    "days": [
        {
            "name": "Upper A",
            "estimated_minutes": 52.5,
            "exercises": [
                {
                    "exercise_id": 20,
                    "slug": "bench-press",
                    "name": "Bench Press",
                    "role": "compound",
                }
            ],
        }
    ],
    "program": PROGRAM_IN_EXAMPLE,
}


class PreviewExercise(BaseModel):
    exercise_id: int
    slug: str
    name: str
    role: Role


class PreviewDay(BaseModel):
    name: str
    estimated_minutes: float = Field(description="Sets, rest and set-up time")
    exercises: list[PreviewExercise]


class ProgramPreview(BaseModel):
    """Not saved: send `program` to `POST /v1/training/programs` to keep it."""

    model_config = ConfigDict(json_schema_extra={"examples": [PREVIEW_EXAMPLE]})

    template: Template
    days: list[PreviewDay]
    program: ProgramIn


@router.post(
    "/programs/generate",
    summary="Generate a program (preview)",
    description=(
        "Deterministic, rule-based program from the exercise library: template by days per week "
        "(2-3 full body, 4 upper/lower, 3 or 6 push/pull/legs), exercises by movement pattern and "
        "equipment, sets/reps/rest by goal, trimmed to `session_minutes`. Nothing is saved: "
        "`program` is a ready body for `POST /v1/training/programs`."
    ),
    response_model=ProgramPreview,
    responses={
        **UNAUTHORIZED,
        400: error("Unsupported days for the template", "upper_lower takes 4 days a week"),
    },
)
async def generate_program(
    principal: CurrentUser, sessionmaker: SessionmakerDep, body: GenerateIn
) -> ProgramPreview:
    async with sessionmaker() as session:
        rows = await ExerciseRepository(session, principal.user_id).with_pattern()
    library = [
        LibraryExercise(
            r.id, r.slug, r.name, Equipment(r.equipment), MovementPattern(r.movement_pattern)
        )
        for r in rows
        if r.movement_pattern is not None
    ]
    request = Request(
        days_per_week=body.days_per_week,
        goal=body.goal,
        equipment=frozenset(body.equipment),
        session_minutes=body.session_minutes,
        template=body.template,
        weeks=body.weeks,
    )
    try:
        program = generate(request, library)
    except GeneratorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ProgramPreview(
        template=program.template,
        days=[
            PreviewDay(
                name=day.name,
                estimated_minutes=float(round(day.minutes, 1)),
                exercises=[
                    PreviewExercise(
                        exercise_id=p.exercise.id,
                        slug=p.exercise.slug,
                        name=p.exercise.name,
                        role=p.role,
                    )
                    for p in day.exercises
                ],
            )
            for day in program.days
        ],
        program=ProgramIn(
            name=program.name,
            goal=program.goal,
            weeks=program.weeks,
            days=[
                ProgramDayIn(
                    name=day.name,
                    exercises=[
                        PlannedExerciseIn(
                            exercise_id=p.exercise.id,
                            sets=p.sets,
                            rep_min=p.rep_min,
                            rep_max=p.rep_max,
                            rest_seconds=p.rest_seconds,
                        )
                        for p in day.exercises
                    ],
                )
                for day in program.days
            ],
        ),
    )


PLATES_EXAMPLE: dict[str, Any] = {
    "target_kg": 101.0,
    "bar_kg": 20.0,
    "per_side": [25.0, 15.0],
    "achieved_kg": 100.0,
    "difference_kg": 1.0,
    "exact": False,
}


class PlatesOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [PLATES_EXAMPLE]})

    target_kg: Kg
    bar_kg: Kg
    per_side: list[Kg] = Field(description="Plates for each side, heaviest first")
    achieved_kg: Kg = Field(description="Target, or the nearest lower weight the plates allow")
    difference_kg: Kg = Field(description="target - achieved; negative when the bar is heavier")
    exact: bool


@router.get(
    "/plates",
    summary="Plates per side",
    description=(
        "Plates to load on each side for `target` kg, from `GYM_BAR_KG` and the `GYM_PLATES` "
        "inventory. If the target cannot be made, the nearest lower weight and the difference."
    ),
    response_model=PlatesOut,
    responses={**UNAUTHORIZED},
)
async def plates(
    principal: CurrentUser,
    settings: SettingsDep,
    target: Annotated[Decimal, Query(ge=0, le=1000, description="kg", examples=["102.5"])],
) -> PlatesOut:
    load = plates_per_side(target, settings.gym_bar_kg, settings.gym_plates)
    return PlatesOut(
        target_kg=load.target_kg,
        bar_kg=load.bar_kg,
        per_side=list(load.per_side),
        achieved_kg=load.achieved_kg,
        difference_kg=load.difference_kg,
        exact=load.exact,
    )
