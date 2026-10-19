"""Build a workout's read model: summary fields, the planned exercises with last performance and
the next-weight suggestion, the sets and the records they beat."""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.settings import Settings
from trainsync.modules.training.math import detect_prs, volume
from trainsync.modules.training.models import LOWER_BODY, Workout, WorkoutSet
from trainsync.modules.training.models import Progression as ProgressionKind
from trainsync.modules.training.progression import Rules, suggest
from trainsync.modules.training.repository import (
    ExerciseRepository,
    ProgramRepository,
    WorkoutRepository,
)
from trainsync.modules.training.schemas import ExerciseOut, RecordOut, SetOut, entry
from trainsync.modules.training.workout_schemas import (
    LastPerformance,
    PerformedSet,
    PlannedExercise,
    SuggestionOut,
    WorkoutDetail,
)

# Sessions of history the suggestion looks at: a deload needs two misses in a row (ADR 0018).
SUGGESTION_SESSIONS = 2


def progression_rules(settings: Settings) -> Rules:
    return Rules(
        increment_kg=settings.progression_increment_kg,
        lower_body_increment_kg=settings.progression_lower_body_increment_kg,
    )


def summary_fields(
    workout: Workout, program_day_name: str | None, sets: list[WorkoutSet]
) -> dict[str, Any]:
    return {
        "id": workout.id,
        "client_id": workout.client_id,
        "program_day_id": workout.program_day_id,
        "program_day_name": program_day_name,
        "started_at": workout.started_at,
        "ended_at": workout.ended_at,
        "notes": workout.notes,
        "set_count": len(sets),
        "exercise_count": len({s.exercise_id for s in sets}),
        "volume_kg": volume(entry(s) for s in sets),
    }


async def day_name(session: AsyncSession, user_id: int, workout: Workout) -> str | None:
    if workout.program_day_id is None:
        return None
    day = await ProgramRepository(session, user_id).day(workout.program_day_id)
    return day.name if day else None


async def planned_exercises(
    session: AsyncSession, user_id: int, workout: Workout, rules: Rules
) -> list[PlannedExercise]:
    if workout.program_day_id is None:
        return []
    planned = (
        await ProgramRepository(session, user_id).day_exercises([workout.program_day_id])
    ).get(workout.program_day_id, [])
    ids = [p.exercise_id for p in planned]
    exercises = await ExerciseRepository(session, user_id).by_ids(ids)
    recent = await WorkoutRepository(session, user_id).recent_performances(
        ids, SUGGESTION_SESSIONS, exclude_workout_id=workout.id
    )
    last = {exercise_id: sessions[0] for exercise_id, sessions in recent.items()}
    started = await _started_at(session, user_id, {sets[0].workout_id for sets in last.values()})
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


async def _started_at(
    session: AsyncSession, user_id: int, workout_ids: set[int]
) -> dict[int, datetime]:
    repo = WorkoutRepository(session, user_id)
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


async def workout_detail(
    session: AsyncSession, user_id: int, workout: Workout, rules: Rules
) -> WorkoutDetail:
    repo = WorkoutRepository(session, user_id)
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
    names = {
        i: e.name
        for i, e in (await ExerciseRepository(session, user_id).by_ids(exercise_ids)).items()
    }
    return WorkoutDetail(
        **summary_fields(workout, await day_name(session, user_id, workout), sets),
        planned=await planned_exercises(session, user_id, workout, rules),
        sets=[SetOut.from_row(s) for s in sets],
        records=[RecordOut.from_record(r, names) for r in records],
    )
