"""P5.5: `/week` shows exactly the numbers of `GET /v1/stats/summary` for the same ranges, with the
real API in-process (Postgres via testcontainers) behind the bot's read-API client."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.factories import create_athlete, strava_activity
from tests.support.messages import NEUTRAL_EN as MSG
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.entrypoints.bot.dispatcher import Commands, week_ranges
from trainsync.modules.activities.repository import ActivityRepository
from trainsync.modules.chat import formatting
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.stats.router import StatsSummary

NOW = datetime(2026, 10, 15, 18, 0, tzinfo=UTC)  # Thursday
KEY = "test-api-key"


@pytest.fixture
async def api_app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def read_api(api_app: FastAPI) -> AsyncIterator[ReadApi]:
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport) as http:
        yield ReadApi(http, "http://api", SecretStr(KEY))


async def _seed(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    athlete_id = await create_athlete(sessionmaker)
    rows = [
        # (id, sport, start, distance m, moving s, elevation m)
        (1, "Run", "2026-10-04T08:00:00Z", 15000.0, 4500, 80.0),  # two weeks ago
        (2, "Run", "2026-10-05T06:00:00Z", 10000.0, 3000, 50.0),  # last week, Monday
        (3, "Ride", "2026-10-11T23:30:00Z", 40000.0, 5400, 400.0),  # last week, Sunday night
        (4, "Run", "2026-10-12T00:10:00Z", 8000.0, 2500, 30.0),  # this week, Monday
        (5, "Ride", "2026-10-14T17:00:00Z", 30100.0, 3720, 350.0),  # this week
        (6, "Run", "2026-10-15T06:30:00Z", 10012.5, 3000, 42.0),  # this week, today
        (7, "Run", "2026-10-13T06:30:00Z", 99999.0, 9999, 999.0),  # this week, deleted
    ]
    async with sessionmaker.begin() as session:
        repo = ActivityRepository(session)
        await repo.upsert_many(
            athlete_id,
            [
                strava_activity(
                    i,
                    sport_type=sport,
                    start_date=start,
                    distance=dist,
                    moving_time=moving,
                    total_elevation_gain=elev,
                )
                for i, sport, start, dist, moving, elev in rows
            ],
        )
        await repo.soft_delete(7)


async def _summary(api_app: FastAPI, start: date, end: date) -> StatsSummary:
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get(
            "/v1/stats/summary",
            params={"from": start.isoformat(), "to": end.isoformat()},
            headers={"X-API-Key": KEY},
        )
    assert response.status_code == 200, response.text
    return StatsSummary.model_validate(response.json())


async def test_week_numbers_equal_stats_summary(
    api_app: FastAPI, read_api: ReadApi, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(sessionmaker)
    text = await Commands(read_api, lambda: NOW, MSG).week()

    (this_from, this_to), (last_from, last_to) = week_ranges(NOW.date())
    this_week = await _summary(api_app, this_from, this_to)
    last_week = await _summary(api_app, last_from, last_to)

    # Hand-computed from the seed: the deleted activity and the other weeks are out.
    assert (this_week.totals.count, this_week.totals.distance_m) == (3, 48112.5)
    assert (last_week.totals.count, last_week.totals.distance_m) == (2, 50000.0)

    lines = text.splitlines()
    assert lines[0] == "This week (12-15 Oct)"
    assert lines[1] == formatting.totals_line(this_week.totals, MSG)
    assert lines[1] == "3 activities · 48.1 km · 2h 33m · ↑ 422 m"
    assert lines[lines.index("Last week (5-11 Oct)") + 1] == formatting.totals_line(
        last_week.totals, MSG
    )
    assert "🚴 Ride: 1 · 30.1 km · 1h 02m" in lines
    assert "🏃 Run: 2 · 18.0 km · 1h 31m" in lines
    assert lines[-1] == "Distance -1.9 km vs last week"
    assert text == formatting.format_week(this_week, last_week, NOW, MSG)
