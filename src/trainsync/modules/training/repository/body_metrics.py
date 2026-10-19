"""Body weight per day (one row per user and date, upserted)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.training.models import BodyMetric


class BodyMetricRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def put(self, day: date, weight_kg: Decimal) -> BodyMetric:
        stmt = insert(BodyMetric).values(user_id=self._user_id, date=day, weight_kg=weight_kg)
        stmt = stmt.on_conflict_do_update(
            index_elements=[BodyMetric.user_id, BodyMetric.date],
            set_={"weight_kg": stmt.excluded.weight_kg},
        )
        return (await self._session.scalars(stmt.returning(BodyMetric))).one()

    async def between(self, start: date | None = None, end: date | None = None) -> list[BodyMetric]:
        stmt = (
            select(BodyMetric).where(BodyMetric.user_id == self._user_id).order_by(BodyMetric.date)
        )
        if start is not None:
            stmt = stmt.where(BodyMetric.date >= start)
        if end is not None:
            stmt = stmt.where(BodyMetric.date <= end)
        return list(await self._session.scalars(stmt))

    async def latest(self, on_or_before: date | None = None) -> BodyMetric | None:
        stmt = (
            select(BodyMetric)
            .where(BodyMetric.user_id == self._user_id)
            .order_by(BodyMetric.date.desc())
            .limit(1)
        )
        if on_or_before is not None:
            stmt = stmt.where(BodyMetric.date <= on_or_before)
        return await self._session.scalar(stmt)
