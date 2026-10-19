from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.factories import create_athlete, strava_activity
from trainsync.modules.activities.models import Activity
from trainsync.modules.activities.repository import ActivityRepository


async def _upsert(
    sessionmaker: async_sessionmaker[AsyncSession], athlete_id: int, activities: list
) -> int:
    async with sessionmaker.begin() as session:
        return await ActivityRepository(session).upsert_many(athlete_id, activities)


async def _synced(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[int, object]:
    async with sessionmaker() as session:
        rows = await session.execute(select(Activity.strava_activity_id, Activity.synced_at))
        return dict(rows.tuples().all())


async def test_upsert_is_idempotent(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    athlete_id = await create_athlete(sessionmaker)
    batch = [strava_activity(i) for i in range(1, 201)]
    assert await _upsert(sessionmaker, athlete_id, batch) == 200
    before = await _synced(sessionmaker)
    assert await _upsert(sessionmaker, athlete_id, batch) == 0
    assert await _synced(sessionmaker) == before


async def test_changed_field_updates_exactly_one_row(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    batch = [strava_activity(i) for i in range(1, 51)]
    await _upsert(sessionmaker, athlete_id, batch)
    before = await _synced(sessionmaker)
    batch[10] = strava_activity(11, name="Renamed")
    assert await _upsert(sessionmaker, athlete_id, batch) == 1
    after = await _synced(sessionmaker)
    assert [k for k in after if after[k] != before[k]] == [11]
    async with sessionmaker() as session:
        row = await session.scalar(select(Activity).where(Activity.strava_activity_id == 11))
    assert row is not None
    assert row.name == "Renamed"
    assert row.raw["name"] == "Renamed"


async def test_mapping_to_columns(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    athlete_id = await create_athlete(sessionmaker)
    activity = strava_activity(
        5,
        distance=10012.5,
        moving_time=3000,
        elapsed_time=3100,
        total_elevation_gain=42.0,
        average_heartrate=150.5,
        kudos_count=7,
    )
    await _upsert(sessionmaker, athlete_id, [activity])
    async with sessionmaker() as session:
        row = await session.scalar(select(Activity))
    assert row is not None
    assert (row.distance_m, row.moving_time_s, row.elapsed_time_s, row.elevation_gain_m) == (
        10012.5,
        3000,
        3100,
        42.0,
    )
    assert row.average_heartrate == 150.5
    assert row.start_date == activity.start_date
    assert row.raw["kudos_count"] == 7


async def test_soft_deleted_activity_restored_by_upsert(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    await _upsert(sessionmaker, athlete_id, [strava_activity(1)])
    async with sessionmaker.begin() as session:
        repo = ActivityRepository(session)
        assert await repo.soft_delete(1) is True
        assert await repo.soft_delete(1) is False  # idempotent
        assert await repo.soft_delete(999) is False  # unknown is fine
    async with sessionmaker() as session:
        assert await session.scalar(select(Activity.deleted_at)) is not None
    assert await _upsert(sessionmaker, athlete_id, [strava_activity(1)]) == 1
    async with sessionmaker() as session:
        assert await session.scalar(select(Activity.deleted_at)) is None


async def test_duplicates_in_one_batch_and_helpers(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    other = await create_athlete(sessionmaker, strava_id=2002)
    batch = [strava_activity(1), strava_activity(2), strava_activity(1, name="later copy")]
    assert await _upsert(sessionmaker, athlete_id, batch) == 2
    assert await _upsert(sessionmaker, other, [strava_activity(100)]) == 1
    assert await _upsert(sessionmaker, athlete_id, []) == 0
    async with sessionmaker.begin() as session:
        repo = ActivityRepository(session)
        assert await repo.max_start_date(athlete_id) == strava_activity(2).start_date
        assert await repo.max_start_date(9999) is None
        assert await repo.delete_for_athlete(athlete_id) == 2
    async with sessionmaker() as session:
        assert (await session.scalars(select(Activity.strava_activity_id))).all() == [100]
