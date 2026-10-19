"""Exercises: the built-in library (shared) plus the user's own custom exercises."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.training.models import Exercise

DEFAULT_SEARCH_LIMIT = 200


class ExerciseRepository:
    """The built-in library (shared) plus the user's own custom exercises."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def _visible(self) -> ColumnElement[bool]:
        return or_(Exercise.user_id.is_(None), Exercise.user_id == self._user_id)

    async def get(self, exercise_id: int) -> Exercise | None:
        return await self._session.scalar(
            select(Exercise).where(Exercise.id == exercise_id, self._visible())
        )

    async def by_slug(self, slug: str) -> Exercise | None:
        return await self._session.scalar(
            select(Exercise)
            .where(Exercise.slug == slug, self._visible())
            .order_by(Exercise.user_id.nulls_first())
            .limit(1)
        )

    async def by_ids(self, ids: Sequence[int]) -> dict[int, Exercise]:
        rows = await self._session.scalars(
            select(Exercise).where(Exercise.id.in_(ids), self._visible())
        )
        return {row.id: row for row in rows}

    async def search(
        self,
        q: str | None = None,
        muscle: str | None = None,
        equipment: Sequence[str] | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[Exercise]:
        """Name/slug substring (case-insensitive), primary or secondary muscle, equipment."""
        stmt = (
            select(Exercise)
            .where(self._visible())
            .order_by(Exercise.name, Exercise.id)
            .limit(limit)
        )
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
        stmt = (
            select(Exercise)
            .where(Exercise.movement_pattern.is_not(None), self._visible())
            .order_by(Exercise.id)
        )
        return list(await self._session.scalars(stmt))

    async def add(self, exercise: Exercise) -> Exercise:
        exercise.user_id = self._user_id
        self._session.add(exercise)
        await self._session.flush()
        return exercise
