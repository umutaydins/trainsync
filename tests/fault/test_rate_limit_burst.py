"""Failure mode: rate limit near / exceeded → backfill pauses, webhooks still processed; a 429
waits for the window reset instead of retrying.

fake_strava and trainsync share one fake clock, so 15-minute windows pass instantly.
"""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.fault.conftest import API_URL, SUBSCRIPTION
from tests.fault.helpers import GET_ACTIVITY, LIST, count_activities, drain_webhooks, fake_calls
from tests.support import fake_webhooks
from tests.support.factories import create_athlete
from tests.support.fake_webhooks import activity_event
from tests.support.strava import fake_backed_client
from trainsync.core.settings import Settings
from trainsync.integrations.strava.budget import RateBudget
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.sync.backfill import run_backfill
from trainsync.modules.sync.context import SyncDeps
from trainsync.modules.sync.webhooks import WebhookDeps

LIMIT_15MIN = 40
TARGET = f"{API_URL}/webhooks/strava"


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(
        seed_activities=300,
        rate_limit_15min=LIMIT_15MIN,
        rate_limit_daily=100_000,
        webhook_subscription_id=SUBSCRIPTION,
    )


@pytest.fixture
async def setup(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    fake_clock: FakeClock,
    integration_settings: Settings,
) -> tuple[int, StravaClient, RateBudget]:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    budget = RateBudget(redis, fake_clock.now)
    strava = fake_backed_client(
        fake_strava_client,
        integration_settings,
        fake_strava_token["access_token"],
        budget=budget,
        clock=fake_clock.now,
    )
    return athlete_id, strava, budget


async def _fire_updates(fake: FakeStravaState, client: httpx.AsyncClient, n: int, t: int) -> None:
    ids = list(fake.activities)[:n]
    events = [
        activity_event(
            i,
            "update",
            owner_id=fake.default_athlete_id,
            subscription_id=SUBSCRIPTION,
            event_time=t + k,
        )
        for k, i in enumerate(ids)
    ]
    report = await fake_webhooks.fire(client, TARGET, events)
    assert report.delivered == n


async def test_backfill_pauses_before_429_while_webhooks_keep_flowing(
    setup: tuple[int, StravaClient, RateBudget],
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_clock: FakeClock,
) -> None:
    athlete_id, strava, budget = setup
    sync = SyncDeps(sessionmaker, strava, budget, fake_clock.now)
    hooks = WebhookDeps(sessionmaker, strava, fake_clock.now)

    windows = 0
    outcome = await run_backfill(sync, athlete_id, per_page=5)
    while outcome.status == "paused":
        windows += 1
        assert windows < 20
        # Backfill paused at 80% of the window: webhook fetches still go through.
        await _fire_updates(fake_strava, fake_strava_client, 3, 1_760_000_000 + windows * 10)
        assert await drain_webhooks(hooks, sessionmaker) == ["upserted"] * 3
        assert outcome.resume_at is not None
        fake_clock.set(outcome.resume_at + timedelta(seconds=1))
        outcome = await run_backfill(sync, athlete_id, per_page=5)

    assert outcome.status == "succeeded"
    assert windows >= 2  # ~60 pages at ≤ 32 low-priority calls per window
    assert await count_activities(sessionmaker) == 300
    assert fake_calls(fake_strava, LIST, "429") == 0
    assert fake_calls(fake_strava, GET_ACTIVITY, "429") == 0
    assert fake_calls(fake_strava, GET_ACTIVITY, "200") == 3 * windows


async def test_429_blocks_both_priorities_until_the_window_resets(
    setup: tuple[int, StravaClient, RateBudget],
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    fake_clock: FakeClock,
) -> None:
    athlete_id, strava, budget = setup
    # Another consumer of the same app credentials uses up the window behind our back.
    auth = {"Authorization": f"Bearer {fake_strava_token['access_token']}"}
    while (await fake_strava_client.get("/api/v3/athlete", headers=auth)).status_code != 429:
        pass
    others_429 = fake_calls(fake_strava, "GET /api/v3/athlete", "429")

    await _fire_updates(fake_strava, fake_strava_client, 1, 1_760_000_000)
    hooks = WebhookDeps(sessionmaker, strava, fake_clock.now)
    assert await drain_webhooks(hooks, sessionmaker) == ["deferred"]
    assert fake_calls(fake_strava, GET_ACTIVITY, "429") == 1

    # Blocked until the quarter hour: no request at all, for either priority.
    sync = SyncDeps(sessionmaker, strava, budget, fake_clock.now)
    before = fake_calls(fake_strava, LIST) + fake_calls(fake_strava, GET_ACTIVITY)
    paused = await run_backfill(sync, athlete_id, per_page=50)
    assert paused.status == "paused"
    assert await drain_webhooks(hooks, sessionmaker) == ["deferred"]
    assert fake_calls(fake_strava, LIST) + fake_calls(fake_strava, GET_ACTIVITY) == before
    assert paused.resume_at is not None
    assert paused.resume_at.minute % 15 == 0
    assert paused.resume_at.second == 0

    fake_clock.set(paused.resume_at + timedelta(seconds=1))
    assert await drain_webhooks(hooks, sessionmaker) == ["upserted"]
    assert fake_calls(fake_strava, GET_ACTIVITY, "429") == 1  # never more than the first
    assert fake_calls(fake_strava, "GET /api/v3/athlete", "429") == others_429
