"""Training tables: exercises, programs, workouts, sets and body metrics (Phase 6)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ColumnElement,
    Select,
    and_,
    delete,
    func,
    literal_column,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import (
    BodyMetric,
    Exercise,
    Program,
    ProgramDay,
    ProgramExercise,
    Workout,
    WorkoutSet,
)


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, exercise_id: int) -> Exercise | None:
        return await self._session.get(Exercise, exercise_id)

    async def by_slug(self, slug: str) -> Exercise | None:
        return await self._session.scalar(select(Exercise).where(Exercise.slug == slug))

    async def by_ids(self, ids: Sequence[int]) -> dict[int, Exercise]:
        rows = await self._session.scalars(select(Exercise).where(Exercise.id.in_(ids)))
        return {row.id: row for row in rows}

    async def search(
        self,
        q: str | None = None,
        muscle: str | None = None,
        equipment: Sequence[str] | None = None,
        limit: int = 200,
    ) -> list[Exercise]:
        """Name/slug substring (case-insensitive), primary or secondary muscle, equipment."""
        stmt = select(Exercise).order_by(Exercise.name, Exercise.id).limit(limit)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(or_(Exercise.name.ilike(pattern), Exercise.slug.ilike(pattern)))
        if muscle:
            stmt = stmt.where(
                or_(
                    Exercise.primary_muscle == muscle, Exercise.secondary_muscles.contains([muscle])
                )
            )
        if equipment:
            stmt = stmt.where(Exercise.equipment.in_(equipment))
        return list(await self._session.scalars(stmt))

    async def with_pattern(self) -> list[Exercise]:
        """Every exercise with a movement pattern (what the program generator picks from)."""
        stmt = select(Exercise).where(Exercise.movement_pattern.is_not(None)).order_by(Exercise.id)
        return list(await self._session.scalars(stmt))

    async def add(self, exercise: Exercise) -> Exercise:
        self._session.add(exercise)
        await self._session.flush()
        return exercise


@dataclass(frozen=True, slots=True)
class ProgramTree:
    program: Program
    days: list[tuple[ProgramDay, list[ProgramExercise]]]


class ProgramRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, program_id: int) -> Program | None:
        return await self._session.get(Program, program_id)

    async def all(self) -> list[Program]:
        stmt = select(Program).order_by(Program.created_at.desc(), Program.id.desc())
        return list(await self._session.scalars(stmt))

    async def active(self) -> Program | None:
        return await self._session.scalar(select(Program).where(Program.active))

    async def tree(self, program_id: int) -> ProgramTree | None:
        program = await self.get(program_id)
        if program is None:
            return None
        days = list(
            await self._session.scalars(
                select(ProgramDay)
                .where(ProgramDay.program_id == program_id)
                .order_by(ProgramDay.day_index)
            )
        )
        exercises = await self.day_exercises([d.id for d in days])
        return ProgramTree(program, [(d, exercises.get(d.id, [])) for d in days])

    async def day(self, program_day_id: int) -> ProgramDay | None:
        return await self._session.get(ProgramDay, program_day_id)

    async def day_exercises(self, day_ids: Sequence[int]) -> dict[int, list[ProgramExercise]]:
        rows = await self._session.scalars(
            select(ProgramExercise)
            .where(ProgramExercise.program_day_id.in_(day_ids))
            .order_by(ProgramExercise.program_day_id, ProgramExercise.position)
        )
        grouped: dict[int, list[ProgramExercise]] = {}
        for row in rows:
            grouped.setdefault(row.program_day_id, []).append(row)
        return grouped

    async def add(
        self, program: Program, days: Sequence[tuple[ProgramDay, Sequence[ProgramExercise]]]
    ) -> Program:
        """Insert a program with its days and exercises (ids are assigned on flush)."""
        self._session.add(program)
        await self._session.flush()
        await self._add_days(program.id, days)
        return program

    async def replace_days(
        self, program_id: int, days: Sequence[tuple[ProgramDay, Sequence[ProgramExercise]]]
    ) -> None:
        """Swap all days and exercises of a program (workouts keep their history; their
        `program_day_id` becomes null)."""
        await self._session.execute(delete(ProgramDay).where(ProgramDay.program_id == program_id))
        await self._add_days(program_id, days)

    async def _add_days(
        self, program_id: int, days: Sequence[tuple[ProgramDay, Sequence[ProgramExercise]]]
    ) -> None:
        for day, exercises in days:
            day.program_id = program_id
            self._session.add(day)
            await self._session.flush()
            for position, exercise in enumerate(exercises):
                exercise.program_day_id = day.id
                exercise.position = position
                self._session.add(exercise)
        await self._session.flush()

    async def activate(self, program_id: int) -> None:
        """Make this the only active program."""
        await self._session.execute(
            update(Program).where(Program.active, Program.id != program_id).values(active=False)
        )
        await self._session.execute(
            update(Program).where(Program.id == program_id).values(active=True)
        )

    async def delete(self, program_id: int) -> bool:
        result = await self._session.execute(
            delete(Program).where(Program.id == program_id).returning(Program.id)
        )
        return result.scalar_one_or_none() is not None


@dataclass(frozen=True, slots=True)
class WorkoutKeyset:
    """Position after the last row of a page: `(started_at, id)` descending."""

    started_at: datetime
    id: int


@dataclass(frozen=True, slots=True)
class SetValues:
    exercise_id: int
    set_index: int
    reps: int
    weight_kg: Decimal
    completed_at: datetime
    rpe: Decimal | None = None
    is_warmup: bool = False
    rest_seconds: int | None = None


class WorkoutRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workout_id: int) -> Workout | None:
        return await self._session.get(Workout, workout_id)

    async def start(
        self, started_at: datetime, program_day_id: int | None = None, notes: str = ""
    ) -> Workout:
        workout = Workout(started_at=started_at, program_day_id=program_day_id, notes=notes)
        self._session.add(workout)
        await self._session.flush()
        return workout

    async def open_workout(self) -> Workout | None:
        """The latest unfinished workout, if any."""
        stmt = (
            select(Workout)
            .where(Workout.ended_at.is_(None))
            .order_by(Workout.started_at.desc(), Workout.id.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def finish(self, workout_id: int, ended_at: datetime) -> None:
        await self._session.execute(
            update(Workout)
            .where(Workout.id == workout_id, Workout.ended_at.is_(None))
            .values(ended_at=ended_at)
        )

    async def delete(self, workout_id: int) -> bool:
        result = await self._session.execute(
            delete(Workout).where(Workout.id == workout_id).returning(Workout.id)
        )
        return result.scalar_one_or_none() is not None

    async def page(self, limit: int, after: WorkoutKeyset | None = None) -> list[Workout]:
        stmt: Select[Workout] = select(Workout).order_by(
            Workout.started_at.desc(), Workout.id.desc()
        )
        if after is not None:
            stmt = stmt.where(
                tuple_(Workout.started_at, Workout.id) < tuple_(after.started_at, after.id)
            )
        return list(await self._session.scalars(stmt.limit(limit)))

    async def sets(self, workout_ids: Sequence[int]) -> list[WorkoutSet]:
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.workout_id.in_(workout_ids))
            .order_by(WorkoutSet.workout_id, WorkoutSet.completed_at, WorkoutSet.id)
        )
        return list(await self._session.scalars(stmt))

    async def put_set(
        self, workout_id: int, client_id: uuid.UUID, values: SetValues
    ) -> tuple[WorkoutSet, bool] | None:
        """Idempotent upsert by `client_id`: (row, created). A retry with the same id updates
        the same row; None if that id already belongs to another workout."""
        fields = {
            "exercise_id": values.exercise_id,
            "set_index": values.set_index,
            "reps": values.reps,
            "weight_kg": values.weight_kg,
            "rpe": values.rpe,
            "is_warmup": values.is_warmup,
            "completed_at": values.completed_at,
            "rest_seconds": values.rest_seconds,
        }
        values_stmt = insert(WorkoutSet).values(
            client_id=client_id, workout_id=workout_id, **fields
        )
        stmt = values_stmt.on_conflict_do_update(
            index_elements=[WorkoutSet.client_id],
            set_={name: values_stmt.excluded[name] for name in fields},
            where=WorkoutSet.workout_id == values_stmt.excluded.workout_id,
        ).returning(WorkoutSet.id, literal_column("xmax = 0", Boolean()).label("created"))
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        stored = await self._session.scalar(
            select(WorkoutSet)
            .where(WorkoutSet.id == row.id)
            .execution_options(populate_existing=True)
        )
        if stored is None:  # pragma: no cover - just returned by the upsert
            raise LookupError(row.id)
        return stored, bool(row.created)

    async def delete_set(self, workout_id: int, client_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(WorkoutSet)
            .where(WorkoutSet.workout_id == workout_id, WorkoutSet.client_id == client_id)
            .returning(WorkoutSet.id)
        )
        return result.scalar_one_or_none() is not None

    async def exercise_history(
        self,
        exercise_ids: Sequence[int] | None,
        before: datetime | None = None,
        exclude_workout_id: int | None = None,
        since: datetime | None = None,
    ) -> list[tuple[Workout, WorkoutSet]]:
        """Every logged set of these exercises (None: of all exercises) with its workout,
        oldest first; `since` ≤ started_at < `before`."""
        stmt = (
            select(Workout, WorkoutSet)
            .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
            .order_by(Workout.started_at, Workout.id, WorkoutSet.set_index, WorkoutSet.id)
        )
        if exercise_ids is not None:
            stmt = stmt.where(WorkoutSet.exercise_id.in_(exercise_ids))
        if since is not None:
            stmt = stmt.where(Workout.started_at >= since)
        if before is not None:
            stmt = stmt.where(Workout.started_at < before)
        if exclude_workout_id is not None:
            stmt = stmt.where(Workout.id != exclude_workout_id)
        result = await self._session.execute(stmt)
        return [(workout, workout_set) for workout, workout_set in result.tuples()]

    async def last_performance(
        self, exercise_ids: Sequence[int], exclude_workout_id: int | None = None
    ) -> dict[int, list[WorkoutSet]]:
        """Per exercise, the working sets of the most recent other workout that logged it."""
        recent = await self.recent_performances(exercise_ids, 1, exclude_workout_id)
        return {exercise_id: sessions[0] for exercise_id, sessions in recent.items()}

    async def recent_performances(
        self, exercise_ids: Sequence[int], sessions: int, exclude_workout_id: int | None = None
    ) -> dict[int, list[list[WorkoutSet]]]:
        """Per exercise, the working sets of its `sessions` most recent other workouts,
        newest workout first."""
        conditions: list[ColumnElement[bool]] = [
            WorkoutSet.exercise_id.in_(exercise_ids),
            WorkoutSet.is_warmup.is_(False),
        ]
        if exclude_workout_id is not None:
            conditions.append(WorkoutSet.workout_id != exclude_workout_id)
        ranked = (
            select(
                WorkoutSet.id,
                func.dense_rank()
                .over(
                    partition_by=WorkoutSet.exercise_id,
                    order_by=(Workout.started_at.desc(), Workout.id.desc()),
                )
                .label("rank"),
            )
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(and_(*conditions))
            .subquery()
        )
        stmt = (
            select(WorkoutSet, ranked.c.rank)
            .join(ranked, ranked.c.id == WorkoutSet.id)
            .where(ranked.c.rank <= sessions)
            .order_by(WorkoutSet.exercise_id, ranked.c.rank, WorkoutSet.set_index, WorkoutSet.id)
        )
        grouped: dict[int, dict[int, list[WorkoutSet]]] = {}
        for row, rank in (await self._session.execute(stmt)).tuples():
            grouped.setdefault(row.exercise_id, {}).setdefault(rank, []).append(row)
        return {
            exercise_id: [by_rank[rank] for rank in sorted(by_rank)]
            for exercise_id, by_rank in grouped.items()
        }


class BodyMetricRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def put(self, day: date, weight_kg: Decimal) -> BodyMetric:
        stmt = insert(BodyMetric).values(date=day, weight_kg=weight_kg)
        stmt = stmt.on_conflict_do_update(
            index_elements=[BodyMetric.date], set_={"weight_kg": stmt.excluded.weight_kg}
        )
        return (await self._session.scalars(stmt.returning(BodyMetric))).one()

    async def between(self, start: date | None = None, end: date | None = None) -> list[BodyMetric]:
        stmt = select(BodyMetric).order_by(BodyMetric.date)
        if start is not None:
            stmt = stmt.where(BodyMetric.date >= start)
        if end is not None:
            stmt = stmt.where(BodyMetric.date <= end)
        return list(await self._session.scalars(stmt))

    async def latest(self, on_or_before: date | None = None) -> BodyMetric | None:
        stmt = select(BodyMetric).order_by(BodyMetric.date.desc()).limit(1)
        if on_or_before is not None:
            stmt = stmt.where(BodyMetric.date <= on_or_before)
        return await self._session.scalar(stmt)
