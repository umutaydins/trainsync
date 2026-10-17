"""Activity rows: one idempotent upsert path shared by backfill, incremental sync and webhooks."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import Activity
from trainsync.strava.models import StravaActivity

_DATA_COLUMNS = (
    "athlete_id",
    "name",
    "sport_type",
    "start_date",
    "distance_m",
    "moving_time_s",
    "elapsed_time_s",
    "elevation_gain_m",
    "average_heartrate",
    "raw",
)


def to_row(athlete_id: int, activity: StravaActivity) -> dict[str, Any]:
    return {
        "strava_activity_id": activity.id,
        "athlete_id": athlete_id,
        "name": activity.name,
        "sport_type": activity.sport_type,
        "start_date": activity.start_date,
        "distance_m": activity.distance,
        "moving_time_s": activity.moving_time,
        "elapsed_time_s": activity.elapsed_time,
        "elevation_gain_m": activity.total_elevation_gain,
        "average_heartrate": activity.average_heartrate,
        "raw": activity.raw(),
    }


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, athlete_id: int, activities: Sequence[StravaActivity]) -> int:
        """Insert new rows, update changed ones; returns how many rows were actually written.

        Rows whose `raw` JSON is unchanged (and that are not soft-deleted) are left alone, so
        re-running a sync is a no-op and does not touch `synced_at`.
        """
        # One statement cannot update the same row twice: keep the last copy of each id.
        unique = {a.id: a for a in activities}
        if not unique:
            return 0
        insert_stmt = insert(Activity).values([to_row(athlete_id, a) for a in unique.values()])
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[Activity.strava_activity_id],
            set_={
                **{col: excluded[col] for col in _DATA_COLUMNS},
                "deleted_at": None,
                "synced_at": func.now(),
            },
            where=or_(
                Activity.raw.is_distinct_from(excluded.raw),
                Activity.athlete_id.is_distinct_from(excluded.athlete_id),
                Activity.deleted_at.is_not(None),
            ),
        ).returning(Activity.id)
        return len((await self._session.execute(stmt)).all())

    async def soft_delete(self, strava_activity_id: int) -> bool:
        """Mark deleted; `False` when unknown or already deleted (both fine: idempotent)."""
        result = await self._session.execute(
            update(Activity)
            .where(Activity.strava_activity_id == strava_activity_id, Activity.deleted_at.is_(None))
            .values(deleted_at=func.now())
            .returning(Activity.id)
        )
        return result.first() is not None

    async def delete_for_athlete(self, athlete_id: int) -> int:
        result = await self._session.execute(
            delete(Activity).where(Activity.athlete_id == athlete_id).returning(Activity.id)
        )
        return len(result.all())

    async def max_start_date(self, athlete_id: int) -> datetime | None:
        latest: datetime | None = await self._session.scalar(
            select(func.max(Activity.start_date)).where(Activity.athlete_id == athlete_id)
        )
        return latest
