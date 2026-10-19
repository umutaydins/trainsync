"""Failure mode: duplicate webhook delivery → dedup key, `ON CONFLICT DO NOTHING`.

Ten copies of one event arrive *concurrently*, racing on the INSERT, the way Strava's retries
can overlap a slow first delivery. Exactly one row, one job, one fetch.
"""

from typing import Any

import httpx
from arq.connections import ArqRedis
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.fault.conftest import API_URL, SUBSCRIPTION
from tests.fault.helpers import GET_ACTIVITY, drain_webhooks, fake_calls, metric
from tests.support import fake_webhooks
from tests.support.factories import create_athlete
from tests.support.fake_webhooks import activity_event
from tests.support.strava import fake_backed_client
from trainsync.core.clock import utc_now
from trainsync.core.settings import Settings
from trainsync.modules.sync.models import WebhookEvent
from trainsync.modules.sync.webhooks import WebhookDeps

TARGET = f"{API_URL}/webhooks/strava"


async def test_concurrent_duplicates_store_one_event_and_fetch_once(
    api_app: FastAPI,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    activity_id = next(iter(fake_strava.activities))
    event = activity_event(
        activity_id,
        "update",
        owner_id=fake_strava.default_athlete_id,
        subscription_id=SUBSCRIPTION,
        event_time=1_760_000_000,
        updates={"title": "Long run"},
    )
    duplicates_before = metric("webhook_events_total", aspect="activity:update", status="duplicate")

    report = await fake_webhooks.fire(
        fake_strava_client, TARGET, [event], mode="duplicate", duplicates=10, concurrency=10
    )
    assert report.delivered == 10
    assert all(len(d.attempts) == 1 for d in report.deliveries)

    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(WebhookEvent)) == 1
    pool: ArqRedis = api_app.state.job_queue.pool
    assert len(await pool.queued_jobs()) == 1
    assert (
        metric("webhook_events_total", aspect="activity:update", status="duplicate")
        - duplicates_before
        == 9
    )

    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    deps = WebhookDeps(sessionmaker, strava, utc_now)
    assert await drain_webhooks(deps, sessionmaker) == ["upserted"]
    assert await drain_webhooks(deps, sessionmaker) == []
    assert fake_calls(fake_strava, GET_ACTIVITY) == 1
