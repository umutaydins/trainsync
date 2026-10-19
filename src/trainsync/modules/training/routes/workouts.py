"""`/v1/training/workouts`: start, log sets (idempotent by client id, ADR 0017), finish, list."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.deps import (
    ClockDep,
    CoachEventsDep,
    SessionmakerDep,
    SettingsDep,
    require_api_key,
)
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.core.jobs import CoachEvents
from trainsync.core.logging import get_logger
from trainsync.core.settings import Settings
from trainsync.modules.activities.router import as_utc
from trainsync.modules.training.math import detect_prs, volume
from trainsync.modules.training.models import LOWER_BODY, Workout, WorkoutSet
from trainsync.modules.training.models import Progression as ProgressionKind
from trainsync.modules.training.progression import Action, Rules, Suggestion, suggest
from trainsync.modules.training.repository import (
    ExerciseRepository,
    ProgramRepository,
    SetValues,
    WorkoutKeyset,
    WorkoutRepository,
)
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
    decode_cursor,
    encode_cursor,
    entry,
)

log = get_logger(__name__)

router = APIRouter(
    prefix="/v1/training", tags=["training"], dependencies=[Depends(require_api_key)]
)

NOT_FOUND = error("Unknown workout", "workout not found")

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
    notes: str = Field(default="", max_length=2000)


class WorkoutFinish(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"ended_at": "2026-10-18T18:35:00Z", "notes": "good"}]}
    )

    ended_at: datetime | None = Field(default=None, description="Default: now")
    notes: str | None = Field(default=None, max_length=2000)


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


class SetIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [SET_IN_EXAMPLE]})

    exercise_id: int
    set_index: int = Field(ge=0, le=100, description="Order of the set within the exercise")
    reps: int = Field(ge=0, le=100)
    weight_kg: WeightIn
    rpe: RpeIn | None = None
    is_warmup: bool = False
    completed_at: datetime = Field(
        description="When the set was done, as the client saw it (part of the idempotent body)"
    )
    rest_seconds: int | None = Field(default=None, ge=0, le=86400)


async def get_or_404(session: AsyncSession, workout_id: int) -> Workout:
    workout = await WorkoutRepository(session).get(workout_id)
    if workout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workout not found")
    return workout


def _summary_fields(
    workout: Workout, day_name: str | None, sets: list[WorkoutSet]
) -> dict[str, Any]:
    return {
        "id": workout.id,
        "client_id": workout.client_id,
        "program_day_id": workout.program_day_id,
        "program_day_name": day_name,
        "started_at": workout.started_at,
        "ended_at": workout.ended_at,
        "notes": workout.notes,
        "set_count": len(sets),
        "exercise_count": len({s.exercise_id for s in sets}),
        "volume_kg": volume(entry(s) for s in sets),
    }


async def planned_exercises(
    session: AsyncSession, workout: Workout, rules: Rules
) -> list[PlannedExercise]:
    if workout.program_day_id is None:
        return []
    planned = (await ProgramRepository(session).day_exercises([workout.program_day_id])).get(
        workout.program_day_id, []
    )
    ids = [p.exercise_id for p in planned]
    exercises = await ExerciseRepository(session).by_ids(ids)
    recent = await WorkoutRepository(session).recent_performances(
        ids, 2, exclude_workout_id=workout.id
    )
    last = {exercise_id: sessions[0] for exercise_id, sessions in recent.items()}
    started = await _started_at(session, {sets[0].workout_id for sets in last.values()})
    return [
        PlannedExercise(
            exercise=ExerciseOut.from_row(exercises[p.exercise_id]),
            sets=p.sets,
            rep_min=p.rep_min,
            rep_max=p.rep_max,
            rest_seconds=p.rest_seconds,
            start_weight_kg=p.start_weight_kg,
            progression=ProgressionKind(p.progression),
            last_performance=_last(last.get(p.exercise_id), started),
            suggestion=SuggestionOut.from_suggestion(
                suggest(
                    [[entry(s) for s in sets] for sets in recent.get(p.exercise_id, [])],
                    p.rep_min,
                    p.rep_max,
                    planned_sets=p.sets,
                    lower_body=exercises[p.exercise_id].primary_muscle in LOWER_BODY,
                    start_weight_kg=p.start_weight_kg,
                    auto=p.progression == ProgressionKind.DOUBLE,
                    rules=rules,
                )
            ),
        )
        for p in planned
    ]


async def _started_at(session: AsyncSession, workout_ids: set[int]) -> dict[int, datetime]:
    repo = WorkoutRepository(session)
    found = {i: await repo.get(i) for i in sorted(workout_ids)}
    return {i: w.started_at for i, w in found.items() if w is not None}


def _last(sets: list[WorkoutSet] | None, started: dict[int, datetime]) -> LastPerformance | None:
    if not sets:
        return None
    return LastPerformance(
        workout_id=sets[0].workout_id,
        started_at=started[sets[0].workout_id],
        sets=[PerformedSet(reps=s.reps, weight_kg=s.weight_kg, rpe=s.rpe) for s in sets],
    )


def progression_rules(settings: Settings) -> Rules:
    return Rules(
        increment_kg=settings.progression_increment_kg,
        lower_body_increment_kg=settings.progression_lower_body_increment_kg,
    )


async def coach_event(events: CoachEvents, job: str, object_id: int) -> None:
    """Best effort (ADR 0030): a queue problem is logged, never fails the write it follows."""
    try:
        await events.coach_event(job, object_id)
    except Exception as exc:
        log.warning("coach_event_not_queued", job=job, object_id=object_id, error=str(exc))


async def workout_detail(session: AsyncSession, workout: Workout, rules: Rules) -> WorkoutDetail:
    repo = WorkoutRepository(session)
    sets = await repo.sets([workout.id])
    exercise_ids = sorted({s.exercise_id for s in sets})
    history = (
        await repo.exercise_history(
            exercise_ids, before=workout.started_at, exclude_workout_id=workout.id
        )
        if exercise_ids
        else []
    )
    records = detect_prs([entry(s) for _, s in history], [entry(s) for s in sets])
    names = {i: e.name for i, e in (await ExerciseRepository(session).by_ids(exercise_ids)).items()}
    return WorkoutDetail(
        **_summary_fields(workout, await _day_name(session, workout), sets),
        planned=await planned_exercises(session, workout, rules),
        sets=[SetOut.from_row(s) for s in sets],
        records=[RecordOut.from_record(r, names) for r in records],
    )


async def _day_name(session: AsyncSession, workout: Workout) -> str | None:
    if workout.program_day_id is None:
        return None
    day = await ProgramRepository(session).day(workout.program_day_id)
    return day.name if day else None


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
            and await ProgramRepository(session).day(body.program_day_id) is None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "program day not found")
        workout, created = await WorkoutRepository(session).start(
            client_id, as_utc(body.started_at) or clock(), body.program_day_id, body.notes
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        detail = await workout_detail(session, workout, progression_rules(settings))
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
    sessionmaker: SessionmakerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(description="`next_cursor` of the previous page")] = None,
) -> WorkoutPage:
    after = decode_cursor(cursor) if cursor else None
    async with sessionmaker() as session:
        repo = WorkoutRepository(session)
        rows = await repo.page(limit + 1, after)
        page, more = rows[:limit], len(rows) > limit
        sets_by_workout: dict[int, list[WorkoutSet]] = {w.id: [] for w in page}
        for s in await repo.sets(list(sets_by_workout)):
            sets_by_workout[s.workout_id].append(s)
        items = [
            WorkoutSummary(**_summary_fields(w, await _day_name(session, w), sets_by_workout[w.id]))
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
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    workout_id: Annotated[int, Path(examples=[42])],
) -> WorkoutDetail:
    async with sessionmaker() as session:
        workout = await get_or_404(session, workout_id)
        return await workout_detail(session, workout, progression_rules(settings))


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
    sessionmaker: SessionmakerDep,
    settings: SettingsDep,
    clock: ClockDep,
    events: CoachEventsDep,
    workout_id: Annotated[int, Path(examples=[42])],
    body: Annotated[
        WorkoutFinish | None,
        Body(openapi_examples={"now": {"value": {}}, "with_notes": {"value": {"notes": "good"}}}),
    ] = None,
) -> WorkoutDetail:
    body = body or WorkoutFinish()
    ended_at = as_utc(body.ended_at) or clock()
    async with sessionmaker.begin() as session:
        workout = await get_or_404(session, workout_id)
        if workout.ended_at is None:
            if ended_at < workout.started_at:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "`ended_at` is before `started_at`"
                )
            workout.ended_at = ended_at
        if body.notes is not None:
            workout.notes = body.notes
        await session.flush()
        detail = await workout_detail(session, workout, progression_rules(settings))
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
    sessionmaker: SessionmakerDep, workout_id: Annotated[int, Path(examples=[42])]
) -> Response:
    async with sessionmaker.begin() as session:
        if not await WorkoutRepository(session).delete(workout_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workout not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    sessionmaker: SessionmakerDep,
    events: CoachEventsDep,
    response: Response,
    workout_id: Annotated[int, Path(examples=[42])],
    client_id: Annotated[uuid.UUID, Path(examples=[SET_EXAMPLE["client_id"]])],
    body: SetIn,
) -> SetOut:
    async with sessionmaker.begin() as session:
        await get_or_404(session, workout_id)
        if await ExerciseRepository(session).get(body.exercise_id) is None:
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
        result = await WorkoutRepository(session).put_set(workout_id, client_id, values)
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
    sessionmaker: SessionmakerDep,
    workout_id: Annotated[int, Path(examples=[42])],
    client_id: Annotated[uuid.UUID, Path(examples=[SET_EXAMPLE["client_id"]])],
) -> Response:
    async with sessionmaker.begin() as session:
        await get_or_404(session, workout_id)
        await WorkoutRepository(session).delete_set(workout_id, client_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
