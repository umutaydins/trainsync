"""Deauthorization (the Strava `athlete` update with `authorized=false`): one transaction."""

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.strava.models import Athlete, OAuthToken


async def deauthorize(session: AsyncSession, athlete_id: int) -> int:
    """Deactivate, delete tokens and activities; returns how many activities were removed.

    The UPDATE locks the athlete row first, so sync pages and webhook upserts that check
    `is_active_locked` wait for this transaction and cannot write the data back afterwards.
    """
    await session.execute(update(Athlete).where(Athlete.id == athlete_id).values(active=False))
    await session.execute(delete(OAuthToken).where(OAuthToken.athlete_id == athlete_id))
    result = await session.execute(
        delete(Activity).where(Activity.athlete_id == athlete_id).returning(Activity.id)
    )
    return len(result.all())
