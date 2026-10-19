import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from arq.connections import ArqRedis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.jobs import create_arq_redis, webhook_job_id
from trainsync.core.settings import Settings
from trainsync.modules.sync.models import WebhookEvent
from trainsync.modules.sync.webhook_repository import MAX_ATTEMPTS, WebhookEventRepository
from trainsync.modules.sync.webhook_retry import STALE_AFTER, retry_job_id, retry_webhooks_once
from trainsync.modules.sync.webhooks import WebhookDeps, process_event

T0 = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
_keys = itertools.count()


@dataclass
class ManualClock:
    now: datetime = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=3, rate_limit_15min=10_000, rate_limit_daily=100_000)


@pytest.fixture
async def pool(integration_settings: Settings) -> Any:
    pool = create_arq_redis(integration_settings)
    yield pool
    await pool.aclose()


async def _queued(pool: ArqRedis) -> list[str]:
    return sorted(job.job_id or "" for job in await pool.queued_jobs())


async def _take(pool: ArqRedis, job_id: str) -> None:
    """Remove a queued job, as if a worker had picked it up and finished."""
    await pool.zrem("arq:queue", job_id)
    await pool.delete(f"arq:job:{job_id}")


async def _insert(
    sessionmaker: async_sessionmaker[AsyncSession], fake: FakeStravaState, **values: Any
) -> int:
    activity_id = next(iter(fake.activities))
    payload = {
        "object_type": "activity",
        "object_id": activity_id,
        "aspect_type": "update",
        "updates": {},
        "owner_id": fake.default_athlete_id,
        "subscription_id": 999,
        "event_time": 1_760_000_000,
    }
    async with sessionmaker.begin() as session:
        event_id = await WebhookEventRepository(session).insert_new(f"key-{next(_keys)}", payload)
        assert event_id is not None
        if values:
            await session.execute(
                update(WebhookEvent).where(WebhookEvent.id == event_id).values(**values)
            )
    return event_id


async def _event(sessionmaker: async_sessionmaker[AsyncSession], event_id: int) -> WebhookEvent:
    async with sessionmaker() as session:
        event = await session.get(WebhookEvent, event_id)
        assert event is not None
        return event


async def test_failing_event_is_retried_with_growing_delays_until_strava_recovers(
    sessionmaker: async_sessionmaker[AsyncSession],
    pool: ArqRedis,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    clock = ManualClock()
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"], clock=clock
    )
    deps = WebhookDeps(sessionmaker, strava, clock)
    event_id = await _insert(sessionmaker, fake_strava)
    fake_strava.update_config({"error_rate": 1.0})

    assert (await process_event(deps, event_id)).status == "failed"
    retry_times = []
    for expected_wait in (2, 4, 8):  # minutes after attempt 1, 2, 3
        last = (await _event(sessionmaker, event_id)).last_attempt_at
        assert last == clock.now
        clock.now = last + timedelta(minutes=expected_wait) - timedelta(seconds=1)
        assert (await retry_webhooks_once(sessionmaker, pool, clock.now))["retried"] == 0
        clock.now += timedelta(seconds=1)
        assert (await retry_webhooks_once(sessionmaker, pool, clock.now))["retried"] == 1
        attempts = (await _event(sessionmaker, event_id)).attempts
        job_id = retry_job_id(event_id, attempts)
        assert await _queued(pool) == [job_id]
        await _take(pool, job_id)
        retry_times.append(clock.now)
        if expected_wait == 8:
            fake_strava.update_config({"error_rate": 0.0})
            assert (await process_event(deps, event_id)).status == "upserted"
        else:
            assert (await process_event(deps, event_id)).status == "failed"

    gaps = [b - a for a, b in itertools.pairwise(retry_times)]
    assert gaps == sorted(gaps)
    event = await _event(sessionmaker, event_id)
    assert (event.status, event.attempts) == ("processed", 4)
    assert (await retry_webhooks_once(sessionmaker, pool, clock.now + timedelta(days=1))) == {
        "retried": 0,
        "recovered": 0,
        "released": 0,
    }


async def test_dead_letters_are_not_retried(
    sessionmaker: async_sessionmaker[AsyncSession], pool: ArqRedis, fake_strava: FakeStravaState
) -> None:
    long_ago = T0 - timedelta(days=2)
    dead = await _insert(
        sessionmaker, fake_strava, status="failed", attempts=MAX_ATTEMPTS, last_attempt_at=long_ago
    )
    last_chance = await _insert(
        sessionmaker,
        fake_strava,
        status="failed",
        attempts=MAX_ATTEMPTS - 1,
        last_attempt_at=long_ago,
    )
    counts = await retry_webhooks_once(sessionmaker, pool, T0)
    assert counts["retried"] == 1
    assert await _queued(pool) == [retry_job_id(last_chance, MAX_ATTEMPTS - 1)]
    async with sessionmaker() as session:
        assert await WebhookEventRepository(session).count_dead() == 1
    assert (await _event(sessionmaker, dead)).status == "failed"


async def test_stale_pending_event_without_job_is_recovered(
    sessionmaker: async_sessionmaker[AsyncSession], pool: ArqRedis, fake_strava: FakeStravaState
) -> None:
    old = T0 - STALE_AFTER - timedelta(seconds=1)
    lost = await _insert(sessionmaker, fake_strava, received_at=old)
    queued = await _insert(sessionmaker, fake_strava, received_at=old, attempts=1)
    await _insert(sessionmaker, fake_strava, received_at=T0 - timedelta(minutes=1))  # too fresh
    await pool.enqueue_job("process_webhook_event", queued, _job_id=webhook_job_id(queued))

    counts = await retry_webhooks_once(sessionmaker, pool, T0)
    assert counts["recovered"] == 1
    assert await _queued(pool) == sorted([webhook_job_id(queued), retry_job_id(lost, 0)])
    # A second sweep sees the recovery job and leaves it alone.
    assert (await retry_webhooks_once(sessionmaker, pool, T0))["recovered"] == 0


async def test_event_stuck_in_processing_is_released_to_failed(
    sessionmaker: async_sessionmaker[AsyncSession], pool: ArqRedis, fake_strava: FakeStravaState
) -> None:
    claimed = T0 - STALE_AFTER - timedelta(minutes=1)
    stuck = await _insert(
        sessionmaker, fake_strava, status="processing", attempts=1, last_attempt_at=claimed
    )
    live = await _insert(
        sessionmaker,
        fake_strava,
        status="processing",
        attempts=1,
        last_attempt_at=T0 - timedelta(minutes=1),
    )
    assert (await retry_webhooks_once(sessionmaker, pool, T0))["released"] == 1
    assert (await _event(sessionmaker, stuck)).status == "failed"
    assert (await _event(sessionmaker, live)).status == "processing"
    # Released at T0; the backoff counts from its last attempt, which is long past.
    assert (await retry_webhooks_once(sessionmaker, pool, T0))["retried"] == 1
