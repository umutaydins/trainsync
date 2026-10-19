import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.factories import create_athlete, strava_activity
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.integrations.strava.breaker import CircuitBreaker
from trainsync.integrations.strava.breaker_status import RedisBreakerPublisher
from trainsync.integrations.strava.budget import RateBudget
from trainsync.integrations.strava.errors import StravaUnavailable
from trainsync.integrations.strava.ratelimit import parse_rate_limit
from trainsync.modules.activities.repository import ActivityRepository
from trainsync.modules.sync.models import SyncKind, SyncStatus, WebhookEvent
from trainsync.modules.sync.repository import SyncRunRepository

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "weekly_stats.json").read_text(encoding="utf-8")
)
KEY = {"X-API-Key": "test-api-key"}
NOW = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


async def _seed_fixture(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    athlete_id = await create_athlete(sessionmaker)
    rows = FIXTURE["activities"]
    async with sessionmaker.begin() as session:
        repo = ActivityRepository(session)
        fields = ("sport_type", "start_date", "distance", "moving_time", "total_elevation_gain")
        await repo.upsert_many(
            athlete_id, [strava_activity(a["id"], **{f: a[f] for f in fields}) for a in rows]
        )
        for a in rows:
            if a.get("deleted"):
                await repo.soft_delete(a["id"])
    return athlete_id


async def _weekly(api: httpx.AsyncClient, **params: Any) -> dict[str, Any]:
    response = await api.get("/v1/stats/weekly", params=params, headers=KEY)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_weekly_stats_match_hand_computed_fixture(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(sessionmaker)
    body = await _weekly(api, **{"from": FIXTURE["from"], "to": FIXTURE["to"]})
    assert body["weeks"] == FIXTURE["expected"]["all"]
    assert (body["from"], body["to"], body["sport_type"]) == (FIXTURE["from"], FIXTURE["to"], None)
    assert body["last_synced_at"] is not None


async def test_sport_filter_and_zero_filled_weeks(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(sessionmaker)
    body = await _weekly(api, **{"from": FIXTURE["from"], "to": FIXTURE["to"], "sport_type": "Run"})
    assert body["weeks"] == FIXTURE["expected"]["Run"]

    nothing = await _weekly(
        api, **{"from": "2026-09-07", "to": "2026-10-04", "sport_type": "Rowing"}
    )
    assert [w["count"] for w in nothing["weeks"]] == [0, 0, 0, 0]
    assert {w["distance_m"] for w in nothing["weeks"]} == {0.0}


async def test_partial_edge_weeks_only_count_days_in_range(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(sessionmaker)
    # Wednesday to Tuesday: #3..#6 in the first week, #7 and #8 in the second.
    body = await _weekly(api, **{"from": "2026-09-09", "to": "2026-09-15"})
    assert [(w["week_start"], w["count"]) for w in body["weeks"]] == [
        ("2026-09-07", 4),
        ("2026-09-14", 2),
    ]


async def test_default_range_is_the_last_12_weeks(api: httpx.AsyncClient) -> None:
    body = await _weekly(api)
    assert len(body["weeks"]) == 12
    assert body["weeks"][-1]["week_start"] == "2026-10-12"  # NOW is Sunday 2026-10-18
    assert body["to"] == "2026-10-18"


@pytest.mark.parametrize(
    "params",
    [{"from": "2026-10-10", "to": "2026-10-01"}, {"from": "2000-01-01", "to": "2026-01-01"}],
    ids=["reversed", "too-long"],
)
async def test_bad_ranges_are_400(params: dict[str, str], api: httpx.AsyncClient) -> None:
    response = await api.get("/v1/stats/weekly", params=params, headers=KEY)
    assert response.status_code == 400


async def _summary(api: httpx.AsyncClient, **params: Any) -> dict[str, Any]:
    response = await api.get("/v1/stats/summary", params=params, headers=KEY)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_summary_matches_hand_computed_fixture(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(sessionmaker)
    expected = FIXTURE["summary"]
    body = await _summary(api, **{"from": FIXTURE["from"], "to": FIXTURE["to"]})
    assert body["totals"] == expected["totals"]
    assert body["by_sport"] == expected["by_sport"]
    assert body["longest"]["id"] == expected["longest"]
    assert body["longest"]["raw"] is None
    assert (body["from"], body["to"], body["sport_type"]) == (FIXTURE["from"], FIXTURE["to"], None)
    assert body["last_synced_at"] is not None


async def test_summary_sport_filter(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(sessionmaker)
    expected = FIXTURE["summary"]
    params = {"from": FIXTURE["from"], "to": FIXTURE["to"], "sport_type": "Run"}
    body = await _summary(api, **params)
    (run,) = (s for s in expected["by_sport"] if s["sport_type"] == "Run")
    assert body["by_sport"] == [run]
    assert body["totals"] == {k: v for k, v in run.items() if k != "sport_type"}
    assert body["longest"]["id"] == expected["longest_Run"]


async def test_summary_of_an_empty_range(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(sessionmaker)
    # The week of 2026-09-21 holds only soft-deleted #13.
    body = await _summary(api, **{"from": "2026-09-21", "to": "2026-09-27"})
    assert body["totals"] == {
        "count": 0,
        "distance_m": 0.0,
        "moving_time_s": 0,
        "elevation_gain_m": 0.0,
    }
    assert body["by_sport"] == []
    assert body["longest"] is None


async def test_summary_defaults_and_reversed_range(api: httpx.AsyncClient) -> None:
    body = await _summary(api)
    assert (body["from"], body["to"]) == ("2026-07-27", "2026-10-18")  # 12 ISO weeks to NOW
    assert body["totals"]["count"] == 0
    assert body["last_synced_at"] is None
    reversed_range = {"from": "2026-10-10", "to": "2026-10-01"}
    response = await api.get("/v1/stats/summary", params=reversed_range, headers=KEY)
    assert response.status_code == 400


async def test_sync_status_reflects_running_backfill_failed_webhook_and_open_circuit(
    api: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
) -> None:
    athlete_id = await create_athlete(sessionmaker, 134815)
    async with sessionmaker.begin() as session:
        runs = SyncRunRepository(session)
        done = await runs.create(athlete_id, SyncKind.INCREMENTAL, {"after": 0}, NOW)
        await runs.set_status(done.id, SyncStatus.SUCCEEDED, NOW)
        running = await runs.create(athlete_id, SyncKind.BACKFILL, {"before": None}, NOW)
        await runs.checkpoint(running.id, {"before": 1}, 200, NOW + timedelta(seconds=5))
        session.add_all(
            [
                WebhookEvent(dedup_key="a", payload={}, status="failed", attempts=2),
                WebhookEvent(dedup_key="b", payload={}, status="failed", attempts=8),
                WebhookEvent(dedup_key="c", payload={}, status="pending"),
                WebhookEvent(dedup_key="d", payload={}, status="processed", processed_at=NOW),
            ]
        )
    await RateBudget(redis, lambda: NOW).record(
        parse_rate_limit({"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "164,600"})
        or pytest.fail("bad headers")
    )
    breaker = CircuitBreaker(
        clock=lambda: NOW, listener=RedisBreakerPublisher(redis, "worker@test:1", lambda: NOW)
    )
    for _ in range(breaker.failure_threshold):
        with pytest.raises(StravaUnavailable):
            async with breaker.guard():
                raise StravaUnavailable("503")

    response = await api.get("/v1/sync/status", headers=KEY)
    assert response.status_code == 200, response.text
    body = response.json()

    (athlete,) = body["athletes"]
    assert athlete["strava_athlete_id"] == 134815
    assert athlete["backfill"]["status"] == "running"
    assert (athlete["backfill"]["pages"], athlete["backfill"]["upserted"]) == (1, 200)
    assert athlete["incremental"]["status"] == "succeeded"
    hooks = body["webhooks"]
    assert (hooks["failed"], hooks["dead_letters"], hooks["pending"]) == (1, 1, 1)
    assert hooks["last_processed_at"] is not None
    assert body["rate_limit"]["short_ratio"] == pytest.approx(0.82)
    assert body["rate_limit"]["daily_ratio"] == pytest.approx(0.3)
    assert body["circuit"]["state"] == "open"
    (process,) = body["circuit"]["processes"]
    assert process["process"] == "worker@test:1"
    assert process["retry_at"] == (NOW + breaker.cooldown).isoformat().replace("+00:00", "Z")


async def test_sync_status_when_nothing_happened_yet(api: httpx.AsyncClient) -> None:
    body = (await api.get("/v1/sync/status", headers=KEY)).json()
    assert body["athletes"] == []
    assert body["rate_limit"] is None
    assert body["circuit"] == {"state": "closed", "processes": []}
    assert body["webhooks"]["dead_letters"] == 0


async def test_stats_and_status_require_api_key(api: httpx.AsyncClient) -> None:
    for path in ("/v1/stats/weekly", "/v1/stats/summary", "/v1/sync/status"):
        assert (await api.get(path)).status_code == 401
