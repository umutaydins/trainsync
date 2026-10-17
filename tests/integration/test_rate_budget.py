from datetime import timedelta
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.settings import Settings
from trainsync.db.models import Activity
from trainsync.strava.budget import RateBudget
from trainsync.strava.client import StravaClient
from trainsync.strava.ratelimit import RateLimitSnapshot, Usage, next_window_reset
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import SyncDeps

LIST_ENDPOINT = "GET /api/v3/athlete/activities"


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=1000, rate_limit_15min=50, rate_limit_daily=100_000)


@pytest.fixture
def budget(redis: Redis, fake_clock: FakeClock) -> RateBudget:
    return RateBudget(redis, fake_clock.now)


@pytest.fixture
def strava(
    fake_strava_client: httpx.AsyncClient,
    integration_settings: Settings,
    fake_strava_token: dict[str, Any],
    budget: RateBudget,
    fake_clock: FakeClock,
) -> StravaClient:
    return fake_backed_client(
        fake_strava_client,
        integration_settings,
        fake_strava_token["access_token"],
        budget=budget,
        clock=fake_clock.now,
    )


def _statuses(fake: FakeStravaState, endpoint: str) -> dict[str, int]:
    counts: dict[str, int] = fake.stats_json()["requests"].get(endpoint, {})
    return counts


def _snapshot(short: int, daily: int = 10) -> RateLimitSnapshot:
    return RateLimitSnapshot(Usage(short, 100, daily, 1000))


async def test_record_allow_and_block_round_trip_through_redis(
    budget: RateBudget, fake_clock: FakeClock, redis: Redis
) -> None:
    assert await budget.latest() is None
    await budget.record(_snapshot(85))
    low, high = await budget.allow("low"), await budget.allow("high")
    assert not low.allowed
    assert low.resume_at == next_window_reset(fake_clock.now())
    assert high.allowed
    latest = await budget.latest()
    assert latest is not None
    assert latest.short_ratio == 0.85
    assert await redis.ttl("ratelimit:latest") > 0

    fake_clock.advance(timedelta(minutes=15))  # next window: the snapshot is stale
    assert (await budget.allow("low")).allowed
    latest = await budget.latest()
    assert latest is not None
    assert latest.short_ratio == 0.0

    reset_at = next_window_reset(fake_clock.now())
    await budget.block_until(reset_at)
    assert (await budget.allow("high")).resume_at == reset_at
    latest = await budget.latest()
    assert latest is not None
    assert latest.blocked_until == reset_at
    fake_clock.set(reset_at)
    assert (await budget.allow("high")).allowed


async def test_backfill_pauses_before_429_and_completes_across_windows(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: StravaClient,
    budget: RateBudget,
    fake_clock: FakeClock,
    fake_strava: FakeStravaState,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    deps = SyncDeps(sessionmaker, strava, budget, fake_clock.now)
    pauses = 0
    outcome = await run_backfill(deps, athlete_id, per_page=10)
    while outcome.status == "paused":
        pauses += 1
        assert outcome.resume_at is not None
        assert pauses < 20
        fake_clock.set(outcome.resume_at + timedelta(seconds=1))
        outcome = await run_backfill(deps, athlete_id, per_page=10)

    assert outcome.status == "succeeded"
    assert pauses >= 2  # ~112 pages at <= 40 low-priority calls per 15-minute window
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Activity)) == 1000
    assert _statuses(fake_strava, LIST_ENDPOINT).get("429", 0) <= 1


async def test_high_priority_fetch_still_works_while_backfill_is_paused(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: StravaClient,
    budget: RateBudget,
    fake_clock: FakeClock,
    fake_strava: FakeStravaState,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    deps = SyncDeps(sessionmaker, strava, budget, fake_clock.now)
    outcome = await run_backfill(deps, athlete_id, per_page=10)
    assert outcome.status == "paused"
    assert not (await budget.allow("low")).allowed

    activity_id = next(iter(fake_strava.activities))
    activity = await strava.get_activity(athlete_id, activity_id, priority="high")
    assert activity.id == activity_id
    assert _statuses(fake_strava, "GET /api/v3/activities/{activity_id}") == {"200": 1}
