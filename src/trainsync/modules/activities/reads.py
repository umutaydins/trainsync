"""Queries behind the read API (`/v1`)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Interval,
    Select,
    and_,
    false,
    func,
    literal,
    select,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.strava.models import Athlete
from trainsync.modules.sync.models import SyncRun, SyncStatus


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

    async def athletes(self, athlete_ids: Sequence[int]) -> list[Athlete]:
        stmt = select(Athlete).where(Athlete.id.in_(athlete_ids)).order_by(Athlete.id)
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

    async def activity(
        self, strava_activity_id: int, athlete_ids: Sequence[int]
    ) -> Activity | None:
        """One stored activity of the given athletes, or None if unknown or soft-deleted."""
        if not athlete_ids:
            return None
        stmt = select(Activity).where(
            Activity.strava_activity_id == strava_activity_id,
            *ActivityFilter(athlete_ids).conditions(),
        )
        return (await self._session.scalars(stmt)).one_or_none()

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

    async def weekly_stats(
        self, activity_filter: ActivityFilter, first_week: date, last_week: date
    ) -> list["WeekStats"]:
        """One row per ISO week (Monday, UTC) from `first_week` to `last_week`, zero-filled.

        The filter's `start_from`/`start_to` still apply to the activities, so partial weeks
        at the edges only count activities inside the range.
        """
        weeks = (
            func.generate_series(
                literal(_midnight(first_week), DateTime()),
                literal(_midnight(last_week), DateTime()),
                literal(timedelta(weeks=1), Interval()),
            )
            .table_valued("week_start")
            .render_derived()
        )
        activity_week = func.date_trunc("week", func.timezone("UTC", Activity.start_date))
        conditions = _conditions(activity_filter)
        stmt = (
            select(weeks.c.week_start, *_totals_columns())
            .select_from(weeks)
            .outerjoin(Activity, and_(activity_week == weeks.c.week_start, *conditions))
            .group_by(weeks.c.week_start)
            .order_by(weeks.c.week_start)
        )
        return [
            WeekStats(row[0].date(), *_totals(row[1:]))
            for row in (await self._session.execute(stmt)).all()
        ]

    async def summary(self, activity_filter: ActivityFilter) -> "Summary":
        """Totals, totals per sport type and the longest activity (by distance) for the filter.

        Three queries, one per block; all aggregation happens in Postgres.
        """
        conditions = _conditions(activity_filter)
        totals = (await self._session.execute(select(*_totals_columns()).where(*conditions))).one()
        by_sport = await self._session.execute(
            select(Activity.sport_type, *_totals_columns())
            .where(*conditions)
            .group_by(Activity.sport_type)
            .order_by(Activity.sport_type)
        )
        longest = await self._session.scalar(
            select(Activity)
            .where(*conditions)
            .order_by(Activity.distance_m.desc(), Activity.start_date.desc(), Activity.id.desc())
            .limit(1)
        )
        return Summary(
            totals=Totals(*_totals(totals)),
            by_sport=[SportTotals(row[0], *_totals(row[1:])) for row in by_sport.all()],
            longest=longest,
        )


@dataclass(frozen=True, slots=True)
class WeekStats:
    week_start: date
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float


@dataclass(frozen=True, slots=True)
class Totals:
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float


@dataclass(frozen=True, slots=True)
class SportTotals:
    sport_type: str
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float


@dataclass(frozen=True, slots=True)
class Summary:
    totals: Totals
    by_sport: list[SportTotals]
    longest: Activity | None


def _conditions(activity_filter: ActivityFilter) -> list[ColumnElement[bool]]:
    return activity_filter.conditions() if activity_filter.athlete_ids else [false()]


def _totals_columns() -> tuple[ColumnElement[Any], ...]:
    """count, distance, moving time, elevation; zeros when no activity matches."""
    return (
        func.count(Activity.id),
        func.coalesce(func.sum(Activity.distance_m), 0.0),
        func.coalesce(func.sum(Activity.moving_time_s), 0),
        func.coalesce(func.sum(Activity.elevation_gain_m), 0.0),
    )


def _totals(values: Sequence[Any]) -> tuple[int, float, int, float]:
    count, distance, moving_time, elevation = values
    return int(count), round(float(distance), 1), int(moving_time), round(float(elevation), 1)


def week_start(day: date) -> date:
    """The Monday of `day`'s ISO week."""
    return day - timedelta(days=day.weekday())


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)  # naive on purpose: compared in UTC
