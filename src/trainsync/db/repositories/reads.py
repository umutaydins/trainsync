"""Queries behind the read API (`/v1`)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import Activity, Athlete, SyncRun, SyncStatus


@dataclass(frozen=True, slots=True)
class ActivityFilter:
    athlete_ids: Sequence[int]
    start_from: datetime | None = None
    start_to: datetime | None = None
    sport_type: str | None = None

    def conditions(self) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            _athlete_condition(self.athlete_ids),
            Activity.deleted_at.is_(None),
        ]
        if self.start_from is not None:
            conditions.append(Activity.start_date >= self.start_from)
        if self.start_to is not None:
            conditions.append(Activity.start_date < self.start_to)
        if self.sport_type is not None:
            conditions.append(Activity.sport_type == self.sport_type)
        return conditions


@dataclass(frozen=True, slots=True)
class Keyset:
    """Position after the last row of a page: `(start_date, id)` in descending order."""

    start_date: datetime
    id: int


def _athlete_condition(athlete_ids: Sequence[int]) -> ColumnElement[bool]:
    # Equality for the usual single athlete, so `(athlete_id, start_date DESC)` serves the order.
    if len(athlete_ids) == 1:
        return Activity.athlete_id == athlete_ids[0]
    return Activity.athlete_id.in_(athlete_ids)


def activity_page_query(
    activity_filter: ActivityFilter, after: Keyset | None, limit: int
) -> Select[Activity]:
    """`limit + 1` rows, newest first; the extra row tells whether there is a next page."""
    stmt = select(Activity).where(*activity_filter.conditions())
    if after is not None:
        stmt = stmt.where(tuple_(Activity.start_date, Activity.id) < (after.start_date, after.id))
    return stmt.order_by(Activity.start_date.desc(), Activity.id.desc()).limit(limit + 1)


class ReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_athlete_ids(self, athlete_id: int | None = None) -> list[int]:
        stmt = select(Athlete.id).where(Athlete.active).order_by(Athlete.id)
        if athlete_id is not None:
            stmt = stmt.where(Athlete.id == athlete_id)
        return list((await self._session.scalars(stmt)).all())

    async def activity_page(
        self, activity_filter: ActivityFilter, after: Keyset | None, limit: int
    ) -> tuple[list[Activity], Keyset | None]:
        if not activity_filter.athlete_ids:
            return [], None
        rows = list(
            (await self._session.scalars(activity_page_query(activity_filter, after, limit))).all()
        )
        if len(rows) <= limit:
            return rows, None
        last = rows[limit - 1]
        return rows[:limit], Keyset(last.start_date, last.id)

    async def last_synced_at(self, athlete_ids: Sequence[int]) -> datetime | None:
        """The newest of: a finished sync run, an activity written by any sync path."""
        if not athlete_ids:
            return None
        run_done = select(func.max(SyncRun.finished_at)).where(
            SyncRun.athlete_id.in_(athlete_ids), SyncRun.status == SyncStatus.SUCCEEDED
        )
        written = select(func.max(Activity.synced_at)).where(Activity.athlete_id.in_(athlete_ids))
        values = [await self._session.scalar(run_done), await self._session.scalar(written)]
        present = [v for v in values if v is not None]
        return max(present) if present else None
