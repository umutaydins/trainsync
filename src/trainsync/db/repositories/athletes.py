"""Athlete rows."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import Athlete


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
