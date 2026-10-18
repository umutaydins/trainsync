"""Training progress (e1RM and best set per session, weekly volume per muscle, personal
records) and body metrics. Every number comes from `trainsync.training.math`."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

from trainsync.api.deps import ClockDep, SessionmakerDep, require_api_key
from trainsync.api.errors import UNAUTHORIZED, error
from trainsync.api.training.common import (
    EXERCISE_EXAMPLE,
    PR_EXAMPLE,
    ExerciseOut,
    Kg,
    RecordOut,
    check_range,
    entry,
)
from trainsync.db.models import Muscle, Workout, WorkoutSet
from trainsync.db.repositories.training import (
    BodyMetricRepository,
    ExerciseRepository,
    WorkoutRepository,
)
from trainsync.training.math import (
    PersonalRecord,
    PrKind,
    SetEntry,
    best_e1rm,
    detect_prs,
    e1rm,
    volume,
    weekly_muscle_volume,
    working,
)

router = APIRouter(
    prefix="/v1/training", tags=["training"], dependencies=[Depends(require_api_key)]
)

DEFAULT_WEEKS = 12
BAD_RANGE = error("`to` before `from`", "`to` is before `from`")

SESSION_EXAMPLE: dict[str, Any] = {
    "workout_id": 42,
    "started_at": "2026-10-18T17:30:00Z",
    "best_set": {"reps": 8, "weight_kg": 82.5, "e1rm_kg": 104.5},
    "e1rm_kg": 104.5,
    "volume_kg": 1890.0,
    "working_sets": 3,
}


class BestSet(BaseModel):
    reps: int
    weight_kg: Kg
    e1rm_kg: Kg | None = Field(description="Epley; null above 12 reps")


class SessionProgress(BaseModel):
    workout_id: int
    started_at: datetime
    best_set: BestSet | None = Field(
        description="Working set with the highest e1RM (then weight); null without working sets"
    )
    e1rm_kg: Kg | None = Field(description="Best e1RM of the session")
    volume_kg: Kg
    working_sets: int


class ExerciseProgress(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"exercise": EXERCISE_EXAMPLE, "sessions": [SESSION_EXAMPLE]}]
        }
    )

    exercise: ExerciseOut
    sessions: list[SessionProgress] = Field(description="Oldest first")


MUSCLE_WEEK_EXAMPLE: dict[str, Any] = {
    "week_start": "2026-10-12",
    "muscle": "chest",
    "sets": 12,
    "volume_kg": 6420.0,
}


class MuscleWeek(BaseModel):
    week_start: date = Field(description="Monday of the ISO week (UTC)")
    muscle: Muscle = Field(description="Primary muscle of the exercises")
    sets: int = Field(description="Working sets")
    volume_kg: Kg


class WeeklyVolume(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [MUSCLE_WEEK_EXAMPLE]}]})

    items: list[MuscleWeek] = Field(description="By week, then muscle; weeks without sets omitted")


CURRENT_PR_EXAMPLE: dict[str, Any] = {
    **PR_EXAMPLE,
    "workout_id": 42,
    "achieved_at": "2026-10-18T17:30:00Z",
}


class CurrentRecord(RecordOut):
    """The standing record; `previous` is the one it beat."""

    model_config = ConfigDict(json_schema_extra={"examples": [CURRENT_PR_EXAMPLE]})

    workout_id: int
    achieved_at: datetime


class RecordList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [CURRENT_PR_EXAMPLE]}]})

    items: list[CurrentRecord]


BODY_EXAMPLE: dict[str, Any] = {"date": "2026-10-18", "weight_kg": 78.4}


class BodyMetricIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"weight_kg": 78.4}]})

    weight_kg: Decimal = Field(gt=0, lt=500, decimal_places=2)


class BodyMetricOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [BODY_EXAMPLE]})

    date: date
    weight_kg: Kg


class BodyMetricList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [BODY_EXAMPLE]}]})

    items: list[BodyMetricOut]


def _day_start(day: date | None) -> datetime | None:
    return datetime.combine(day, time(), UTC) if day is not None else None


def _day_end(day: date | None) -> datetime | None:
    return datetime.combine(day + timedelta(days=1), time(), UTC) if day is not None else None


def best_set(sets: list[SetEntry]) -> BestSet | None:
    candidates = [s for s in working(sets) if s.reps >= 1]
    if not candidates:
        return None
    top = max(
        candidates,
        key=lambda s: (e1rm(s.weight_kg, s.reps) or Decimal(-1), s.weight_kg, s.reps),
    )
    return BestSet(reps=top.reps, weight_kg=top.weight_kg, e1rm_kg=e1rm(top.weight_kg, top.reps))


def _by_workout(rows: list[tuple[Workout, WorkoutSet]]) -> list[tuple[Workout, list[SetEntry]]]:
    grouped: dict[int, tuple[Workout, list[SetEntry]]] = {}
    for workout, row in rows:
        grouped.setdefault(workout.id, (workout, []))[1].append(entry(row))
    return list(grouped.values())


@router.get(
    "/exercises/{exercise_id}/progress",
    summary="Progress of one exercise",
    description=(
        "Per workout that logged the exercise (oldest first): best set, best e1RM (Epley, "
        "1-12 reps), working volume. `from`/`to` are inclusive UTC dates."
    ),
    response_model=ExerciseProgress,
    responses={
        **UNAUTHORIZED,
        400: BAD_RANGE,
        404: error("Unknown exercise", "exercise not found"),
    },
)
async def exercise_progress(
    sessionmaker: SessionmakerDep,
    exercise_id: Annotated[int, Path(examples=[20])],
    start: Annotated[date | None, Query(alias="from", examples=["2026-07-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-31"])] = None,
) -> ExerciseProgress:
    check_range(start, end)
    async with sessionmaker() as session:
        exercise = await ExerciseRepository(session).get(exercise_id)
        if exercise is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "exercise not found")
        rows = await WorkoutRepository(session).exercise_history(
            [exercise_id], since=_day_start(start), before=_day_end(end)
        )
    return ExerciseProgress(
        exercise=ExerciseOut.from_row(exercise),
        sessions=[
            SessionProgress(
                workout_id=workout.id,
                started_at=workout.started_at,
                best_set=best_set(sets),
                e1rm_kg=best_e1rm(sets),
                volume_kg=volume(sets),
                working_sets=len(working(sets)),
            )
            for workout, sets in _by_workout(rows)
        ],
    )


@router.get(
    "/volume/weekly",
    summary="Weekly volume per muscle",
    description=(
        "Working sets and kg (reps x weight) per ISO week and primary muscle. `from`/`to` are "
        "inclusive UTC dates; default the last 12 weeks."
    ),
    response_model=WeeklyVolume,
    responses={**UNAUTHORIZED, 400: BAD_RANGE},
)
async def weekly_volume(
    sessionmaker: SessionmakerDep,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-31"])] = None,
) -> WeeklyVolume:
    end = end or clock().date()
    start = start or end - timedelta(weeks=DEFAULT_WEEKS)
    check_range(start, end)
    async with sessionmaker() as session:
        rows = await WorkoutRepository(session).exercise_history(
            None, since=_day_start(start), before=_day_end(end)
        )
        exercises = await ExerciseRepository(session).by_ids(
            sorted({s.exercise_id for _, s in rows})
        )
    weeks = weekly_muscle_volume(
        [(w.started_at.astimezone(UTC).date(), entry(s)) for w, s in rows],
        {i: e.primary_muscle for i, e in exercises.items()},
    )
    return WeeklyVolume(
        items=[
            MuscleWeek(week_start=week, muscle=Muscle(muscle), sets=v.sets, volume_kg=v.volume_kg)
            for (week, muscle), v in weeks.items()
        ]
    )


def current_records(
    sessions: list[tuple[Workout, list[SetEntry]]],
) -> list[tuple[PersonalRecord, Workout]]:
    """Replay workouts oldest first; the last record of each (exercise, kind, reps) stands."""
    history: dict[int, list[SetEntry]] = defaultdict(list)
    standing: dict[tuple[int, PrKind, int | None], tuple[PersonalRecord, Workout]] = {}
    for workout, sets in sessions:
        earlier = [s for exercise_id in {s.exercise_id for s in sets} for s in history[exercise_id]]
        for record in detect_prs(earlier, sets):
            standing[(record.exercise_id, record.kind, record.reps)] = (record, workout)
        for s in sets:
            history[s.exercise_id].append(s)
    return list(standing.values())


@router.get(
    "/prs",
    summary="Personal records",
    description=(
        "Standing records per exercise: heaviest weight per rep count, best e1RM and best session "
        "volume, with the workout that set them."
    ),
    response_model=RecordList,
    responses={**UNAUTHORIZED},
)
async def personal_records(
    sessionmaker: SessionmakerDep,
    exercise_id: Annotated[int | None, Query(description="Only this exercise")] = None,
) -> RecordList:
    async with sessionmaker() as session:
        rows = await WorkoutRepository(session).exercise_history(
            [exercise_id] if exercise_id is not None else None
        )
        names = {
            i: e.name
            for i, e in (
                await ExerciseRepository(session).by_ids(sorted({s.exercise_id for _, s in rows}))
            ).items()
        }
    records = sorted(
        current_records(_by_workout(rows)),
        key=lambda pair: (names.get(pair[0].exercise_id, ""), pair[0].kind, pair[0].reps or 0),
    )
    return RecordList(
        items=[
            CurrentRecord(
                **RecordOut.from_record(record, names).model_dump(),
                workout_id=workout.id,
                achieved_at=workout.started_at,
            )
            for record, workout in records
        ]
    )


@router.put(
    "/body-metrics/{day}",
    summary="Record body weight for a day",
    description="Upsert by date (idempotent).",
    response_model=BodyMetricOut,
    responses={**UNAUTHORIZED},
)
async def put_body_metric(
    sessionmaker: SessionmakerDep,
    day: Annotated[date, Path(examples=["2026-10-18"])],
    body: BodyMetricIn,
) -> BodyMetricOut:
    async with sessionmaker.begin() as session:
        row = await BodyMetricRepository(session).put(day, body.weight_kg)
        return BodyMetricOut(date=row.date, weight_kg=row.weight_kg)


@router.get(
    "/body-metrics",
    summary="List body metrics",
    description="Oldest first; `from`/`to` inclusive.",
    response_model=BodyMetricList,
    responses={**UNAUTHORIZED, 400: BAD_RANGE},
)
async def list_body_metrics(
    sessionmaker: SessionmakerDep,
    start: Annotated[date | None, Query(alias="from", examples=["2026-09-01"])] = None,
    end: Annotated[date | None, Query(alias="to", examples=["2026-10-31"])] = None,
) -> BodyMetricList:
    check_range(start, end)
    async with sessionmaker() as session:
        rows = await BodyMetricRepository(session).between(start, end)
    return BodyMetricList(items=[BodyMetricOut(date=r.date, weight_kg=r.weight_kg) for r in rows])
