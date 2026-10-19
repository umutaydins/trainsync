"""Workouts and their sets: idempotent starts and set upserts by client id (ADR 0017), pages,
history and recent performances."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ColumnElement,
    Select,
    and_,
    delete,
    func,
    literal_column,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.training.models import Workout, WorkoutSet


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
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def _mine(self) -> ColumnElement[bool]:
        return Workout.user_id == self._user_id

    async def get(self, workout_id: int) -> Workout | None:
        return await self._session.scalar(
            select(Workout).where(Workout.id == workout_id, self._mine())
        )

    async def start(
        self,
        client_id: uuid.UUID,
        started_at: datetime,
        program_day_id: int | None = None,
        notes: str = "",
    ) -> tuple[Workout, bool]:
        """Idempotent start by `client_id`: (workout, created). The first start wins; a repeat
        returns that workout unchanged."""
        stmt = (
            insert(Workout)
            .values(
                user_id=self._user_id,
                client_id=client_id,
                started_at=started_at,
                program_day_id=program_day_id,
                notes=notes,
            )
            .on_conflict_do_nothing(index_elements=[Workout.user_id, Workout.client_id])
            .returning(Workout.id)
        )
        created = await self._session.scalar(stmt) is not None
        workout = await self._session.scalar(
            select(Workout)
            .where(Workout.client_id == client_id, self._mine())
            .execution_options(populate_existing=True)
        )
        if workout is None:  # pragma: no cover - inserted or already there
            raise LookupError(client_id)
        return workout, created

    async def open_workout(self) -> Workout | None:
        """The latest unfinished workout, if any."""
        stmt = (
            select(Workout)
            .where(Workout.ended_at.is_(None), self._mine())
            .order_by(Workout.started_at.desc(), Workout.id.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def latest_for_days(self, program_day_ids: Sequence[int]) -> Workout | None:
        """The most recent workout that followed one of these program days."""
        if not program_day_ids:
            return None
        stmt = (
            select(Workout)
            .where(Workout.program_day_id.in_(program_day_ids), self._mine())
            .order_by(Workout.started_at.desc(), Workout.id.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def finish(self, workout_id: int, ended_at: datetime) -> None:
        await self._session.execute(
            update(Workout)
            .where(Workout.id == workout_id, Workout.ended_at.is_(None), self._mine())
            .values(ended_at=ended_at)
        )

    async def delete(self, workout_id: int) -> bool:
        result = await self._session.execute(
            delete(Workout).where(Workout.id == workout_id, self._mine()).returning(Workout.id)
        )
        return result.scalar_one_or_none() is not None

    async def page(self, limit: int, after: WorkoutKeyset | None = None) -> list[Workout]:
        stmt: Select[Workout] = (
            select(Workout)
            .where(self._mine())
            .order_by(Workout.started_at.desc(), Workout.id.desc())
        )
        if after is not None:
            stmt = stmt.where(
                tuple_(Workout.started_at, Workout.id) < tuple_(after.started_at, after.id)
            )
        return list(await self._session.scalars(stmt.limit(limit)))

    async def sets(self, workout_ids: Sequence[int]) -> list[WorkoutSet]:
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.workout_id.in_(workout_ids), WorkoutSet.user_id == self._user_id)
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
            user_id=self._user_id, client_id=client_id, workout_id=workout_id, **fields
        )
        stmt = values_stmt.on_conflict_do_update(
            index_elements=[WorkoutSet.user_id, WorkoutSet.client_id],
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
            .where(
                WorkoutSet.workout_id == workout_id,
                WorkoutSet.client_id == client_id,
                WorkoutSet.user_id == self._user_id,
            )
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
            .where(self._mine())
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
        return [(workout, workout_set) for workout, workout_set in result]

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
            WorkoutSet.user_id == self._user_id,
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
        for row, rank in await self._session.execute(stmt):
            grouped.setdefault(row.exercise_id, {}).setdefault(rank, []).append(row)
        return {
            exercise_id: [by_rank[rank] for rank in sorted(by_rank)]
            for exercise_id, by_rank in grouped.items()
        }
