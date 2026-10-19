"""`/v1/training/workouts`: start (idempotent by client id, ADR 0017), list, read, finish, delete.

The sets of a workout are in `sets.py`; the read model is built in `workout_detail.py`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, Query, Response, status

from trainsync.core.deps import ClockDep, CoachEventsDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.activities.router import as_utc
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.training.models import WorkoutSet
from trainsync.modules.training.repository import (
    ProgramRepository,
    WorkoutKeyset,
    WorkoutRepository,
)
from trainsync.modules.training.routes.workout_common import (
    NOT_FOUND,
    WORKOUT_ID_EXAMPLE,
    coach_event,
    get_or_404,
)
from trainsync.modules.training.schemas import decode_cursor, encode_cursor
from trainsync.modules.training.workout_detail import (
    day_name,
    progression_rules,
    summary_fields,
    workout_detail,
)
from trainsync.modules.training.workout_schemas import (
    SUMMARY_EXAMPLE,
    WorkoutDetail,
    WorkoutFinish,
    WorkoutPage,
    WorkoutStart,
    WorkoutSummary,
)

router = APIRouter(prefix="/v1/training", tags=["training"])

DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE = 50, 200


@router.put(
    "/workouts/{client_id}",
    summary="Start a workout (idempotent)",
    description=(
        "Starts a workout, free or from a program day, under a client-generated `client_id` "
        "(ADR 0017): `201` when it started the workout, `200` when a workout with this id "
        "already exists (a retry, a double tap or a check-in edit), returned unchanged: the "
        "first start wins, whatever the repeat's body says. The response lists the day's "
        "planned exercises with the last performance of each (working sets of the most recent "
        "other workout that logged it)."
    ),
    status_code=status.HTTP_200_OK,
    response_model=WorkoutDetail,
    responses={
        **UNAUTHORIZED,
        201: {"description": "Started", "model": WorkoutDetail},
        400: error("Unknown program day", "program day not found"),
    },
)
async def start_workout(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    events: CoachEventsDep,
    response: Response,
    client_id: Annotated[uuid.UUID, Path(examples=[SUMMARY_EXAMPLE["client_id"]])],
    body: Annotated[
        WorkoutStart | None,
        Body(
            openapi_examples={
                "program_day": {"value": {"program_day_id": 11}},
                "free": {"value": {"notes": "hotel gym"}},
            }
        ),
    ] = None,
) -> WorkoutDetail:
    body = body or WorkoutStart()
    async with sessionmaker.begin() as session:
        if (
            body.program_day_id is not None
            and await ProgramRepository(session, principal.user_id).day(body.program_day_id) is None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "program day not found")
        workout, created = await WorkoutRepository(session, principal.user_id).start(
            client_id, as_utc(body.started_at) or clock(), body.program_day_id, body.notes
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        detail = await workout_detail(
            session, principal.user_id, workout, progression_rules(settings)
        )
    if created:
        await coach_event(events, "coach_workout_started", detail.id)
    return detail


@router.get(
    "/workouts",
    summary="List workouts",
    description="Newest first, keyset-paginated (ADR 0009): pass `next_cursor` back as `cursor`.",
    response_model=WorkoutPage,
    responses={**UNAUTHORIZED, 400: error("Invalid cursor", "invalid cursor")},
)
async def list_workouts(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[str | None, Query(description="`next_cursor` of the previous page")] = None,
) -> WorkoutPage:
    after = decode_cursor(cursor) if cursor else None
    async with sessionmaker() as session:
        repo = WorkoutRepository(session, principal.user_id)
        rows = await repo.page(limit + 1, after)
        page, more = rows[:limit], len(rows) > limit
        sets_by_workout: dict[int, list[WorkoutSet]] = {w.id: [] for w in page}
        for s in await repo.sets(list(sets_by_workout)):
            sets_by_workout[s.workout_id].append(s)
        items = [
            WorkoutSummary(
                **summary_fields(
                    w, await day_name(session, principal.user_id, w), sets_by_workout[w.id]
                )
            )
            for w in page
        ]
    next_cursor = (
        encode_cursor(WorkoutKeyset(page[-1].started_at, page[-1].id)) if more and page else None
    )
    return WorkoutPage(items=items, next_cursor=next_cursor)


@router.get(
    "/workouts/{workout_id}",
    summary="Get a workout",
    description="Sets, volume, records hit and (for a program day) the plan with last performance.",
    response_model=WorkoutDetail,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def get_workout(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    workout_id: Annotated[int, Path(examples=[WORKOUT_ID_EXAMPLE])],
) -> WorkoutDetail:
    async with sessionmaker() as session:
        workout = await get_or_404(session, principal.user_id, workout_id)
        return await workout_detail(
            session, principal.user_id, workout, progression_rules(settings)
        )


@router.post(
    "/workouts/{workout_id}/finish",
    summary="Finish a workout",
    description=(
        "Sets `ended_at` (default now); an empty workout can be finished. Finishing again keeps "
        "the first `ended_at` (idempotent) but updates `notes` when sent."
    ),
    response_model=WorkoutDetail,
    responses={
        **UNAUTHORIZED,
        400: error("`ended_at` before the start", "`ended_at` is before `started_at`"),
        404: NOT_FOUND,
    },
)
async def finish_workout(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    events: CoachEventsDep,
    workout_id: Annotated[int, Path(examples=[WORKOUT_ID_EXAMPLE])],
    body: Annotated[
        WorkoutFinish | None,
        Body(openapi_examples={"now": {"value": {}}, "with_notes": {"value": {"notes": "good"}}}),
    ] = None,
) -> WorkoutDetail:
    body = body or WorkoutFinish()
    ended_at = as_utc(body.ended_at) or clock()
    async with sessionmaker.begin() as session:
        workout = await get_or_404(session, principal.user_id, workout_id)
        if workout.ended_at is None:
            if ended_at < workout.started_at:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "`ended_at` is before `started_at`"
                )
            workout.ended_at = ended_at
        if body.notes is not None:
            workout.notes = body.notes
        await session.flush()
        detail = await workout_detail(
            session, principal.user_id, workout, progression_rules(settings)
        )
    await coach_event(events, "coach_workout_finished", detail.id)
    return detail


@router.delete(
    "/workouts/{workout_id}",
    summary="Delete a workout",
    description="Deletes the workout and its sets.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**UNAUTHORIZED, 404: NOT_FOUND},
)
async def delete_workout(
    principal: CurrentUser,
    sessionmaker: SessionmakerDep,
    workout_id: Annotated[int, Path(examples=[WORKOUT_ID_EXAMPLE])],
) -> Response:
    async with sessionmaker.begin() as session:
        if not await WorkoutRepository(session, principal.user_id).delete(workout_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workout not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
