"""Athlete rows."""

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import Activity, Athlete, OAuthToken


class AthleteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_connected(self, strava_athlete_id: int) -> int:
        """Create or re-activate the athlete; returns our `athletes.id`."""
        stmt = (
            insert(Athlete)
            .values(strava_athlete_id=strava_athlete_id, active=True)
            .on_conflict_do_update(
                index_elements=[Athlete.strava_athlete_id], set_={"active": True}
            )
            .returning(Athlete.id)
        )
        athlete_id: int = (await self._session.execute(stmt)).scalar_one()
        return athlete_id

    async def by_strava_id(self, strava_athlete_id: int) -> Athlete | None:
        return await self._session.scalar(
            select(Athlete).where(Athlete.strava_athlete_id == strava_athlete_id)
        )

    async def is_active_locked(self, athlete_id: int) -> bool:
        """Active, read `FOR SHARE`: writers of the athlete's data call this in their transaction,
        so they wait for a concurrent deauthorization and then see `False`."""
        active: bool | None = await self._session.scalar(
            select(Athlete.active).where(Athlete.id == athlete_id).with_for_update(read=True)
        )
        return bool(active)

    async def deauthorize(self, athlete_id: int) -> int:
        """Deactivate, delete tokens and activities; returns how many activities were removed.

        The UPDATE locks the athlete row first, so sync pages and webhook upserts that check
        `is_active_locked` wait for this transaction and cannot write the data back afterwards.
        """
        await self._session.execute(
            update(Athlete).where(Athlete.id == athlete_id).values(active=False)
        )
        await self._session.execute(delete(OAuthToken).where(OAuthToken.athlete_id == athlete_id))
        result = await self._session.execute(
            delete(Activity).where(Activity.athlete_id == athlete_id).returning(Activity.id)
        )
        return len(result.all())
