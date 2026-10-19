"""Small builders for DB rows and Strava models used across integration tests."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.integrations.strava.models import StravaActivity
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
    sessionmaker: async_sessionmaker[AsyncSession], strava_id: int = 1001, *, active: bool = True
) -> int:
    async with sessionmaker.begin() as session:
        athlete = Athlete(strava_athlete_id=strava_id, active=active)
        session.add(athlete)
        await session.flush()
        return athlete.id
