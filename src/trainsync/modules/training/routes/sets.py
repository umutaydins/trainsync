"""`/v1/training/workouts/{workout_id}/sets`: log, correct and delete sets, idempotent by the
client-generated id (ADR 0017)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status

from trainsync.core.deps import CoachEventsDep, SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.activities.router import as_utc
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.training.repository import (
    ExerciseRepository,
    SetValues,
    WorkoutRepository,
)
from trainsync.modules.training.routes.workout_common import (
    NOT_FOUND,
    WORKOUT_ID_EXAMPLE,
    coach_event,
    get_or_404,
)
from trainsync.modules.training.schemas import SET_EXAMPLE, SetOut
from trainsync.modules.training.workout_schemas import SetIn

router = APIRouter(prefix="/v1/training", tags=["training"])


@router.put(
    "/workouts/{workout_id}/sets/{client_id}",
    summary="Log or correct a set (idempotent)",
    description=(
        "Upsert by the client-generated `client_id` (ADR 0017): the first call creates the set "
        "(`201`), a retry or a correction with the same id updates that same set (`200`, same "
        "body for the same input). Retries and double taps never create a second set. An id "
        "already used in another workout is `409`."
    ),
    response_model=SetOut,
    responses={
        **UNAUTHORIZED,
        201: {"description": "Created", "model": SetOut},
        400: error("Unknown exercise", "exercise not found"),
        404: NOT_FOUND,
        409: error("Id used by another workout", "client_id belongs to another workout"),
    },
)
async def put_set(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    events: CoachEventsDep,
    response: Response,
    workout_id: Annotated[int, Path(examples=[WORKOUT_ID_EXAMPLE])],
    client_id: Annotated[uuid.UUID, Path(examples=[SET_EXAMPLE["client_id"]])],
    body: SetIn,
) -> SetOut:
    async with sessionmaker.begin() as session:
        await get_or_404(session, principal.user_id, workout_id)
        if await ExerciseRepository(session, principal.user_id).get(body.exercise_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "exercise not found")
        values = SetValues(
            exercise_id=body.exercise_id,
            set_index=body.set_index,
            reps=body.reps,
            weight_kg=body.weight_kg,
            completed_at=as_utc(body.completed_at) or body.completed_at,
            rpe=body.rpe,
            is_warmup=body.is_warmup,
            rest_seconds=body.rest_seconds,
        )
        result = await WorkoutRepository(session, principal.user_id).put_set(
            workout_id, client_id, values
        )
        if result is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "client_id belongs to another workout")
        row, created = result
        out = SetOut.from_row(row)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    if created:
        await coach_event(events, "coach_set_logged", row.id)
    return out


@router.delete(
    "/workouts/{workout_id}/sets/{client_id}",
    summary="Delete a set",
    description="Idempotent: deleting a set that is not there is also `204`.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def delete_set(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    workout_id: Annotated[int, Path(examples=[WORKOUT_ID_EXAMPLE])],
    client_id: Annotated[uuid.UUID, Path(examples=[SET_EXAMPLE["client_id"]])],
) -> Response:
    async with sessionmaker.begin() as session:
        await get_or_404(session, principal.user_id, workout_id)
        await WorkoutRepository(session, principal.user_id).delete_set(workout_id, client_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
