import statistics
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.api import deps
from trainsync.api.webhooks import EXAMPLE_EVENT
from trainsync.core.settings import Settings
from trainsync.db.models import WebhookEvent
from trainsync.main import create_app
from trainsync.sync.queue import ArqJobQueue, webhook_job_id

LATENCY_SAMPLES = 300
P99_BUDGET_MS = 100.0
# Test settings use STRAVA_WEBHOOK_SUBSCRIPTION_ID=999.
EVENT: dict[str, Any] = {**EXAMPLE_EVENT, "subscription_id": 999}


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


async def _queued(app: FastAPI) -> list[str]:
    queue: ArqJobQueue = app.state.job_queue
    return [job.job_id or "" for job in await queue.pool.queued_jobs()]


async def _events(sessionmaker: async_sessionmaker[AsyncSession]) -> list[WebhookEvent]:
    async with sessionmaker() as session:
        return list((await session.scalars(select(WebhookEvent))).all())


async def test_same_event_five_times_stores_one_row_and_one_job(
    app: FastAPI, api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    statuses = []
    for _ in range(5):
        response = await api.post("/webhooks/strava", json=EVENT)
        assert response.status_code == 200
        statuses.append(response.json()["status"])
    assert statuses == ["queued"] + ["duplicate"] * 4

    (event,) = await _events(sessionmaker)
    assert (event.status, event.attempts) == ("pending", 0)
    assert event.payload == EVENT
    assert await _queued(app) == [webhook_job_id(event.id)]


async def test_handler_makes_no_outbound_http_calls(api: httpx.AsyncClient) -> None:
    # No routes: any outbound httpx request would fail with "not mocked".
    with respx.mock(assert_all_mocked=True) as router:
        for aspect in ("create", "update", "delete"):
            response = await api.post("/webhooks/strava", json={**EVENT, "aspect_type": aspect})
            assert response.status_code == 200
    assert router.calls.call_count == 0


async def test_enqueue_failure_still_acknowledges_and_keeps_the_event(
    app: FastAPI, api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    class BrokenQueue:
        async def enqueue_webhook_event(self, event_id: int) -> bool:
            raise ConnectionError("redis down")

    app.dependency_overrides[deps.get_job_queue] = BrokenQueue
    response = await api.post("/webhooks/strava", json=EVENT)
    assert response.status_code == 200
    (event,) = await _events(sessionmaker)
    assert event.status == "pending"


async def test_p99_latency_under_100ms(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    durations_ms = []
    for n in range(LATENCY_SAMPLES):
        event: dict[str, Any] = {**EVENT, "object_id": n, "event_time": 1_700_000_000 + n}
        started = time.perf_counter()
        response = await api.post("/webhooks/strava", json=event)
        durations_ms.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200
    p50 = statistics.median(durations_ms)
    p99 = statistics.quantiles(durations_ms, n=100)[98]
    print(f"webhook POST over {LATENCY_SAMPLES} requests: p50={p50:.1f} ms p99={p99:.1f} ms")
    assert p99 < P99_BUDGET_MS
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(WebhookEvent)) == 300
