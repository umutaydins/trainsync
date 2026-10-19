"""Athlete rows. An athlete belongs to exactly one user, a user has at most one (ADR 0037)."""

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.strava.models import Athlete


class AthleteTakenError(Exception):
    """The Strava athlete is bound to another user, or this user already has another one."""


async def athlete_user_id(session: AsyncSession, athlete_id: int) -> int:
    """The user an athlete belongs to (worker jobs are keyed by athlete)."""
    user_id = await session.scalar(select(Athlete.user_id).where(Athlete.id == athlete_id))
    if user_id is None:
        raise LookupError(f"athlete {athlete_id}")
    return int(user_id)


class AthleteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_connected(self, strava_athlete_id: int, user_id: int) -> int:
        """Create or re-activate the user's athlete; returns our `athletes.id`.

        Raises `AthleteTakenError` when the Strava athlete belongs to someone else, or when the
        user still has a different, connected Strava athlete. A different athlete the user
        disconnected earlier is replaced (its data went with the disconnect).
        """
        existing = await self.by_strava_id(strava_athlete_id)
        if existing is not None and existing.user_id != user_id:
            raise AthleteTakenError("this Strava account is connected to another user")
        mine = await self.for_user(user_id)
        if mine is not None and mine.strava_athlete_id != strava_athlete_id:
            if mine.active:
                raise AthleteTakenError("disconnect your current Strava account first")
            await self._session.execute(delete(Athlete).where(Athlete.id == mine.id))
        stmt = (
            insert(Athlete)
            .values(strava_athlete_id=strava_athlete_id, user_id=user_id, active=True)
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

    async def for_user(self, user_id: int) -> Athlete | None:
        return await self._session.scalar(select(Athlete).where(Athlete.user_id == user_id))

    async def set_active(self, athlete_id: int, *, active: bool) -> None:
        await self._session.execute(
            update(Athlete).where(Athlete.id == athlete_id).values(active=active)
        )

    async def is_active_locked(self, athlete_id: int) -> bool:
        """Active, read `FOR SHARE`: writers of the athlete's data call this in their transaction,
        so they wait for a concurrent deauthorization and then see `False`."""
        active: bool | None = await self._session.scalar(
            select(Athlete.active).where(Athlete.id == athlete_id).with_for_update(read=True)
        )
        return bool(active)
