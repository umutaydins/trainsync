"""`daily_checkins`: one row per local day, upserted by date (P6.9, ADR 0020)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.checkin.models import CheckinStatus, DailyCheckin


@dataclass(frozen=True, slots=True)
class CheckinValues:
    status: CheckinStatus
    workout_id: int | None = None
    reason_note: str | None = None
    sleep_hours: Decimal | None = None
    energy_1_5: int | None = None
    body_weight_kg: Decimal | None = None


class CheckinRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, day: date) -> DailyCheckin | None:
        return await self._session.scalar(select(DailyCheckin).where(DailyCheckin.date == day))

    async def put(
        self, day: date, values: CheckinValues, now: datetime
    ) -> tuple[DailyCheckin, bool]:
        """Idempotent upsert by date: (row, created). Every field is replaced (PUT)."""
        fields = {
            "status": values.status.value,
            "workout_id": values.workout_id,
            "reason_note": values.reason_note,
            "sleep_hours": values.sleep_hours,
            "energy_1_5": values.energy_1_5,
            "body_weight_kg": values.body_weight_kg,
            "updated_at": now,
        }
        values_stmt = insert(DailyCheckin).values(date=day, created_at=now, **fields)
        stmt = values_stmt.on_conflict_do_update(
            index_elements=[DailyCheckin.date],
            set_={name: values_stmt.excluded[name] for name in fields},
        ).returning(DailyCheckin.id, literal_column("xmax = 0", Boolean()).label("created"))
        row = (await self._session.execute(stmt)).one()
        stored = await self._session.scalar(
            select(DailyCheckin)
            .where(DailyCheckin.id == row.id)
            .execution_options(populate_existing=True)
        )
        if stored is None:  # pragma: no cover - just returned by the upsert
            raise LookupError(row.id)
        return stored, bool(row.created)

    async def between(self, start: date, end: date) -> list[DailyCheckin]:
        stmt = (
            select(DailyCheckin)
            .where(DailyCheckin.date >= start, DailyCheckin.date <= end)
            .order_by(DailyCheckin.date)
        )
        return list(await self._session.scalars(stmt))

    async def statuses(self, until: date) -> dict[date, CheckinStatus]:
        """Every status up to `until`, for streaks (one short row per day ever checked in)."""
        stmt = select(DailyCheckin.date, DailyCheckin.status).where(DailyCheckin.date <= until)
        return {day: CheckinStatus(status) for day, status in await self._session.execute(stmt)}
