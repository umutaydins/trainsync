"""Queries behind the read API (`/v1`)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

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

from trainsync.db.models import Activity, Athlete, SyncRun, SyncStatus, WebhookEvent
from trainsync.db.repositories.webhook_events import MAX_ATTEMPTS


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
        conditions = activity_filter.conditions() if activity_filter.athlete_ids else [false()]
        stmt = (
            select(
                weeks.c.week_start,
                func.count(Activity.id),
                func.coalesce(func.sum(Activity.distance_m), 0.0),
                func.coalesce(func.sum(Activity.moving_time_s), 0),
                func.coalesce(func.sum(Activity.elevation_gain_m), 0.0),
            )
            .select_from(weeks)
            .outerjoin(Activity, and_(activity_week == weeks.c.week_start, *conditions))
            .group_by(weeks.c.week_start)
            .order_by(weeks.c.week_start)
        )
        return [
            WeekStats(
                week_start=row[0].date(),
                count=row[1],
                distance_m=round(float(row[2]), 1),
                moving_time_s=int(row[3]),
                elevation_gain_m=round(float(row[4]), 1),
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def latest_runs(self, athlete_ids: Sequence[int]) -> dict[tuple[int, str], SyncRun]:
        """The newest run per (athlete, kind)."""
        if not athlete_ids:
            return {}
        newest = (
            select(func.max(SyncRun.id))
            .where(SyncRun.athlete_id.in_(athlete_ids))
            .group_by(SyncRun.athlete_id, SyncRun.kind)
        )
        runs = await self._session.scalars(select(SyncRun).where(SyncRun.id.in_(newest)))
        return {(run.athlete_id, run.kind): run for run in runs}

    async def webhook_summary(self) -> "WebhookSummary":
        received, processed = (
            await self._session.execute(
                select(func.max(WebhookEvent.received_at), func.max(WebhookEvent.processed_at))
            )
        ).one()
        by_status = await self._session.execute(
            select(WebhookEvent.status, func.count()).group_by(WebhookEvent.status)
        )
        counts: dict[str, int] = {status: count for status, count in by_status.all()}
        dead = await self._session.scalar(
            select(func.count())
            .select_from(WebhookEvent)
            .where(WebhookEvent.status == "failed", WebhookEvent.attempts >= MAX_ATTEMPTS)
        )
        return WebhookSummary(
            last_received_at=received,
            last_processed_at=processed,
            pending=counts.get("pending", 0),
            processing=counts.get("processing", 0),
            failed=counts.get("failed", 0) - (dead or 0),
            dead_letters=dead or 0,
        )


@dataclass(frozen=True, slots=True)
class WeekStats:
    week_start: date
    count: int
    distance_m: float
    moving_time_s: int
    elevation_gain_m: float


@dataclass(frozen=True, slots=True)
class WebhookSummary:
    last_received_at: datetime | None
    last_processed_at: datetime | None
    pending: int
    processing: int
    failed: int  # will be retried
    dead_letters: int  # attempts exhausted


def week_start(day: date) -> date:
    """The Monday of `day`'s ISO week."""
    return day - timedelta(days=day.weekday())


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)  # naive on purpose: compared in UTC
