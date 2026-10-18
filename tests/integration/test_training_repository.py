"""P6.1: training tables and repositories against Postgres."""

import asyncio
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import resources

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.db.models import Exercise, Program, ProgramDay, ProgramExercise, WorkoutSet
from trainsync.db.repositories.training import (
    BodyMetricRepository,
    ExerciseRepository,
    ProgramRepository,
    SetValues,
    WorkoutRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)


def seed_count() -> int:
    seed = resources.files("trainsync.training").joinpath("seed_exercises.json")
    return len(json.loads(seed.read_text(encoding="utf-8")))


async def exercise_id(session: AsyncSession, slug: str) -> int:
    exercise = await ExerciseRepository(session).by_slug(slug)
    assert exercise is not None
    return exercise.id


async def test_seeded_library_loads(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(Exercise))
        assert count == seed_count()
        repo = ExerciseRepository(session)
        bench = await repo.by_slug("bench-press")
        assert bench is not None
        assert (bench.primary_muscle, bench.equipment, bench.is_custom) == (
            "chest",
            "barbell",
            False,
        )
        triceps = {e.slug for e in await repo.search(muscle="triceps")}
        assert {"triceps-pushdown", "bench-press"} <= triceps  # primary and secondary
        bodyweight_back = await repo.search(muscle="back", equipment=["bodyweight"])
        assert {e.slug for e in bodyweight_back} >= {"pull-up", "inverted-row"}
        assert [e.slug for e in await repo.search(q="DEADLIFT")][:1] == ["deadlift"]


async def test_custom_exercises_are_cleaned_between_tests_but_the_seed_stays(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        await ExerciseRepository(session).add(
            Exercise(
                slug="landmine-press",
                name="Landmine Press",
                primary_muscle="shoulders",
                equipment="barbell",
                is_custom=True,
            )
        )
    async with sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(Exercise))
        assert count == seed_count() + 1


async def test_put_set_is_idempotent_by_client_id(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        bench = await exercise_id(session, "bench-press")
        workout = await WorkoutRepository(session).start(T0)
    client_id = uuid.uuid4()
    values = SetValues(bench, 0, 5, Decimal("100"), T0 + timedelta(minutes=5))

    async with sessionmaker.begin() as session:
        first = await WorkoutRepository(session).put_set(workout.id, client_id, values)
    async with sessionmaker.begin() as session:
        again = await WorkoutRepository(session).put_set(workout.id, client_id, values)
    assert first is not None
    assert again is not None
    assert first[1] is True
    assert again[1] is False
    assert first[0].id == again[0].id

    # A corrected retry updates the same row.
    fixed = SetValues(bench, 0, 6, Decimal("100"), T0 + timedelta(minutes=5))
    async with sessionmaker.begin() as session:
        updated = await WorkoutRepository(session).put_set(workout.id, client_id, fixed)
    assert updated is not None
    assert updated[0].reps == 6
    assert updated[1] is False

    async with sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(WorkoutSet))
    assert count == 1


async def test_concurrent_puts_store_one_set(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        bench = await exercise_id(session, "bench-press")
        workout = await WorkoutRepository(session).start(T0)
    client_id = uuid.uuid4()
    values = SetValues(bench, 0, 5, Decimal("100"), T0)

    async def put() -> bool:
        async with sessionmaker.begin() as session:
            result = await WorkoutRepository(session).put_set(workout.id, client_id, values)
            assert result is not None
            return result[1]

    created = await asyncio.gather(*(put() for _ in range(5)))
    assert sorted(created) == [False, False, False, False, True]
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(WorkoutSet)) == 1


async def test_a_client_id_cannot_move_to_another_workout(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        bench = await exercise_id(session, "bench-press")
        repo = WorkoutRepository(session)
        first, second = await repo.start(T0), await repo.start(T0 + timedelta(days=1))
    client_id = uuid.uuid4()
    values = SetValues(bench, 0, 5, Decimal("100"), T0)
    async with sessionmaker.begin() as session:
        assert await WorkoutRepository(session).put_set(first.id, client_id, values) is not None
    async with sessionmaker.begin() as session:
        assert await WorkoutRepository(session).put_set(second.id, client_id, values) is None


async def test_last_performance_is_the_latest_other_workout_without_warmups(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        bench = await exercise_id(session, "bench-press")
        squat = await exercise_id(session, "back-squat")
        repo = WorkoutRepository(session)
        older, newer, current = (
            await repo.start(T0),
            await repo.start(T0 + timedelta(days=2)),
            await repo.start(T0 + timedelta(days=4)),
        )
        for workout, weight in ((older, "90"), (newer, "95"), (current, "100")):
            await repo.put_set(
                workout.id, uuid.uuid4(), SetValues(bench, 0, 10, Decimal(40), T0, is_warmup=True)
            )
            for index in (1, 2):
                await repo.put_set(
                    workout.id, uuid.uuid4(), SetValues(bench, index, 5, Decimal(weight), T0)
                )
        await repo.put_set(older.id, uuid.uuid4(), SetValues(squat, 0, 5, Decimal(140), T0))

    async with sessionmaker() as session:
        last = await WorkoutRepository(session).last_performance(
            [bench, squat], exclude_workout_id=current.id
        )
    assert [(s.workout_id, s.weight_kg) for s in last[bench]] == [
        (newer.id, Decimal("95.00")),
        (newer.id, Decimal("95.00")),
    ]
    assert [s.workout_id for s in last[squat]] == [older.id]


async def test_programs_tree_and_a_single_active_program(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        bench = await exercise_id(session, "bench-press")
        squat = await exercise_id(session, "back-squat")
        repo = ProgramRepository(session)

        def day(index: int, name: str, exercise: int) -> tuple[ProgramDay, list[ProgramExercise]]:
            planned = ProgramExercise(
                exercise_id=exercise, sets=3, rep_min=8, rep_max=12, rest_seconds=90
            )
            return ProgramDay(day_index=index, name=name), [planned]

        first = await repo.add(
            Program(name="A", goal="hypertrophy", days_per_week=2, weeks=8),
            [day(0, "Upper", bench), day(1, "Lower", squat)],
        )
        second = await repo.add(
            Program(name="B", goal="strength", days_per_week=1, weeks=4), [day(0, "Full", squat)]
        )
        await repo.activate(first.id)
        await repo.activate(second.id)

    async with sessionmaker() as session:
        repo = ProgramRepository(session)
        active = await repo.active()
        assert active is not None
        assert active.id == second.id
        tree = await repo.tree(first.id)
        assert tree is not None
        assert [(d.name, [e.exercise_id for e in ex]) for d, ex in tree.days] == [
            ("Upper", [bench]),
            ("Lower", [squat]),
        ]
        assert tree.days[0][1][0].progression == "double"

    with pytest.raises(IntegrityError):
        async with sessionmaker.begin() as session:
            await session.execute(Program.__table__.update().values(active=True))


async def test_body_metrics_upsert_by_date(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker.begin() as session:
        repo = BodyMetricRepository(session)
        await repo.put(date(2026, 10, 12), Decimal("78.4"))
        await repo.put(date(2026, 10, 14), Decimal("78.0"))
        stored = await repo.put(date(2026, 10, 12), Decimal("78.2"))
        assert stored.weight_kg == Decimal("78.20")
    async with sessionmaker() as session:
        repo = BodyMetricRepository(session)
        assert [(m.date.day, m.weight_kg) for m in await repo.between()] == [
            (12, Decimal("78.20")),
            (14, Decimal("78.00")),
        ]
        latest = await repo.latest(on_or_before=date(2026, 10, 13))
        assert latest is not None
        assert latest.date == date(2026, 10, 12)
