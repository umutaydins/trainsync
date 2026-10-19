"""Small builders for DB rows and Strava models used across integration tests."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import ScalarSelect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import OWNER_ID
from trainsync.core.security import UNUSABLE_HASH
from trainsync.integrations.strava.models import StravaActivity
from trainsync.modules.auth.models import UserRole
from trainsync.modules.auth.repository import UserRepository
from trainsync.modules.strava.models import Athlete

BASE_DATE = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)


def strava_activity(activity_id: int, **overrides: object) -> StravaActivity:
    data: dict[str, object] = {
        "id": activity_id,
        "name": f"Activity {activity_id}",
        "sport_type": "Run",
        "start_date": (BASE_DATE + timedelta(hours=activity_id)).isoformat(),
        "distance": 5000.0 + activity_id,
        "moving_time": 1500,
        "elapsed_time": 1600,
        "total_elevation_gain": 10.0,
    }
    data.update(overrides)
    return StravaActivity.model_validate(data)


async def create_athlete(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava_id: int = 1001,
    *,
    active: bool = True,
    user_id: int | None = None,
) -> int:
    """An athlete of `user_id`; by default the owner's, or (the owner has one already) a new
    user's: one athlete per user (ADR 0037)."""
    async with sessionmaker.begin() as session:
        if user_id is None:
            taken = await session.scalar(select(Athlete.id).where(Athlete.user_id == OWNER_ID))
            user_id = OWNER_ID if taken is None else await _new_user(session, strava_id)
        athlete = Athlete(user_id=user_id, strava_athlete_id=strava_id, active=active)
        session.add(athlete)
        await session.flush()
        return athlete.id


async def _new_user(session: AsyncSession, strava_id: int) -> int:
    user = await UserRepository(session).add(
        email=f"athlete{strava_id}@example.com",
        password_hash=UNUSABLE_HASH,
        display_name=f"Athlete {strava_id}",
        timezone="UTC",
        role=UserRole.USER,
    )
    return user.id


def owner_of(athlete_id: int) -> ScalarSelect[int]:
    """`user_id` for a row of this athlete (activities, sync runs): the athlete's user."""
    return select(Athlete.user_id).where(Athlete.id == athlete_id).scalar_subquery()
