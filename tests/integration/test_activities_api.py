from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.support.factories import BASE_DATE, create_athlete, strava_activity
from trainsync.core.settings import Settings
from trainsync.db.models import Athlete
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.reads import ActivityFilter, Keyset, activity_page_query
from trainsync.main import create_app

KEY = {"X-API-Key": "test-api-key"}
SPORTS = ("Run", "Ride", "Swim")


@pytest.fixture
async def api(integration_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(integration_settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            yield client


async def _seed(
    sessionmaker: async_sessionmaker[AsyncSession], athlete_id: int, ids: range
) -> None:
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(
            athlete_id, [strava_activity(i, sport_type=SPORTS[i % 3]) for i in ids]
        )


async def _all_pages(api: httpx.AsyncClient, **params: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        query = {**params, **({"cursor": cursor} if cursor else {})}
        response = await api.get("/v1/activities", params=query, headers=KEY)
        assert response.status_code == 200, response.text
        body = response.json()
        items += body["items"]
        cursor = body["next_cursor"]
        if cursor is None:
            return items


async def test_paging_returns_every_activity_once_despite_concurrent_inserts(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    await _seed(sessionmaker, athlete_id, range(1, 1001))

    seen: list[dict[str, Any]] = []
    cursor = None
    new_id = 5000
    pages = 0
    while True:
        params: dict[str, Any] = {"limit": 200, **({"cursor": cursor} if cursor else {})}
        body = (await api.get("/v1/activities", params=params, headers=KEY)).json()
        seen += body["items"]
        cursor = body["next_cursor"]
        pages += 1
        if cursor is None:
            break
        # Between pages: a brand-new activity and a late upload of an old one.
        new_id += 1
        async with sessionmaker.begin() as session:
            await ActivityRepository(session).upsert_many(
                athlete_id,
                [
                    strava_activity(
                        new_id, start_date=(BASE_DATE + timedelta(days=400)).isoformat()
                    ),
                    strava_activity(
                        new_id + 100,
                        start_date=(BASE_DATE - timedelta(days=1, minutes=new_id)).isoformat(),
                    ),
                ],
            )

    ids = [item["id"] for item in seen]
    assert len(ids) == len(set(ids)), "an activity was returned twice"
    assert set(range(1, 1001)) <= set(ids)
    keys = [(item["start_date"], item["id"]) for item in seen]
    assert keys == sorted(keys, reverse=True)
    assert pages >= 5
    assert all(item["raw"] is None for item in seen)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, lambda i: True),
        ({"sport_type": "Run"}, lambda i: SPORTS[i % 3] == "Run"),
        ({"from": "2026-01-03T00:00:00Z"}, lambda i: i >= 42),
        ({"to": "2026-01-03"}, lambda i: i < 42),
        (
            {
                "from": "2026-01-02T12:00:00+00:00",
                "to": "2026-01-04T00:00:00Z",
                "sport_type": "Ride",
            },
            lambda i: 30 <= i < 66 and SPORTS[i % 3] == "Ride",
        ),
        ({"from": "2026-01-04", "to": "2026-01-03"}, lambda i: False),
    ],
    ids=["none", "sport", "from", "to-date-only", "all-three", "empty-range"],
)
async def test_filters_combine(
    params: dict[str, str],
    expected: Any,
    api: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Activity i starts at 2026-01-01T06:00Z + i hours.
    athlete_id = await create_athlete(sessionmaker)
    await _seed(sessionmaker, athlete_id, range(1, 101))
    items = await _all_pages(api, limit=7, **params)
    assert sorted(item["id"] for item in items) == [i for i in range(1, 101) if expected(i)]


async def test_excludes_soft_deleted_and_inactive_athletes_and_filters_by_athlete(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    one = await create_athlete(sessionmaker, 1001)
    two = await create_athlete(sessionmaker, 1002)
    gone = await create_athlete(sessionmaker, 1003)
    await _seed(sessionmaker, one, range(1, 6))
    await _seed(sessionmaker, two, range(6, 9))
    await _seed(sessionmaker, gone, range(9, 11))
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).soft_delete(3)
        await session.execute(update(Athlete).where(Athlete.id == gone).values(active=False))

    assert sorted(i["id"] for i in await _all_pages(api)) == [1, 2, 4, 5, 6, 7, 8]
    assert sorted(i["id"] for i in await _all_pages(api, athlete_id=two)) == [6, 7, 8]
    assert await _all_pages(api, athlete_id=gone) == []

    body = (
        await api.get("/v1/activities", params={"include": "raw", "limit": 1}, headers=KEY)
    ).json()
    assert body["items"][0]["raw"]["id"] == body["items"][0]["id"]
    assert body["last_synced_at"] is not None


async def test_valid_key_is_200_and_wrong_key_is_401(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/activities", headers=KEY)).status_code == 200
    assert (await api.get("/v1/activities", headers={"X-API-Key": "nope"})).status_code == 401
    empty = (await api.get("/v1/activities", headers=KEY)).json()
    assert empty == {"items": [], "next_cursor": None, "last_synced_at": None}


async def test_detail_returns_one_activity_with_optional_raw(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    await _seed(sessionmaker, athlete_id, range(1, 4))

    response = await api.get("/v1/activities/2", headers=KEY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["activity"]["id"] == 2
    assert body["activity"]["athlete_id"] == athlete_id
    assert body["activity"]["sport_type"] == SPORTS[2]
    assert body["activity"]["raw"] is None
    assert body["last_synced_at"] is not None

    raw = (await api.get("/v1/activities/2", params={"include": "raw"}, headers=KEY)).json()
    assert raw["activity"]["raw"]["id"] == 2


async def test_detail_is_404_for_unknown_soft_deleted_or_inactive(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    one = await create_athlete(sessionmaker, 1001)
    gone = await create_athlete(sessionmaker, 1002)
    await _seed(sessionmaker, one, range(1, 4))
    await _seed(sessionmaker, gone, range(4, 6))
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).soft_delete(3)
        await session.execute(update(Athlete).where(Athlete.id == gone).values(active=False))

    for activity_id in (999, 3, 4):
        response = await api.get(f"/v1/activities/{activity_id}", headers=KEY)
        assert response.status_code == 404, activity_id
        assert response.json() == {"detail": "activity not found"}


async def test_detail_requires_api_key(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(sessionmaker, await create_athlete(sessionmaker), range(1, 2))
    assert (await api.get("/v1/activities/1")).status_code == 401
    assert (await api.get("/v1/activities/1", headers={"X-API-Key": "nope"})).status_code == 401


async def test_page_query_uses_athlete_start_date_index(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO athletes (strava_athlete_id)"
                " SELECT 5000 + g FROM generate_series(1, 20) g"
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO activities (strava_activity_id, athlete_id, name, sport_type,
                    start_date, distance_m, moving_time_s, elapsed_time_s, elevation_gain_m, raw)
                SELECT g, a.id, 'a', (ARRAY['Run','Ride','Swim'])[1 + g % 3],
                    timestamptz '2020-01-01' + g * interval '37 minutes', 1000, 300, 320, 5, '{}'
                FROM generate_series(1, 60000) g
                JOIN athletes a ON a.strava_athlete_id = 5000 + 1 + g % 20
                """
            )
        )
        await conn.execute(text("ANALYZE activities"))
        athlete_id = await conn.scalar(text("SELECT min(id) FROM athletes"))

        for after in (None, Keyset(datetime(2022, 1, 1, tzinfo=UTC), 30000)):
            stmt = activity_page_query(ActivityFilter([athlete_id]), after, 50)
            sql = str(
                stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            )
            plan = "\n".join((await conn.execute(text(f"EXPLAIN {sql}"))).scalars().all())
            assert "ix_activities_athlete_start_date" in plan, plan
            assert "Seq Scan" not in plan, plan
