"""P4.1: worker metrics after a real (fake_strava-backed) backfill, and job ids in job logs."""

import dataclasses
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import structlog
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.config import FakeStravaConfig
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.jobs import create_arq_redis
from trainsync.core.settings import Settings
from trainsync.entrypoints.worker.settings import shutdown, startup
from trainsync.integrations.strava.errors import RateLimited
from trainsync.integrations.strava.models import StravaActivity
from trainsync.modules.sync.backfill import backfill
from trainsync.modules.sync.context import CTX_KEY, WorkerContext


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=250, rate_limit_15min=10_000, rate_limit_daily=100_000)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture
async def worker_ctx(
    integration_settings: Settings,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """A worker started by the real `startup` (metrics server included), with its Strava client
    swapped for one that talks to the in-process fake."""
    port = _free_port()
    settings = integration_settings.model_copy(update={"worker_metrics_port": port})
    redis = create_arq_redis(settings)
    ctx: dict[str, Any] = {"settings": settings, "redis": redis, "metrics_port": port}
    await startup(ctx)
    wc: WorkerContext = ctx[CTX_KEY]
    strava = fake_backed_client(
        fake_strava_client, settings, fake_strava_token["access_token"], budget=None
    )
    ctx[CTX_KEY] = dataclasses.replace(wc, strava=strava)
    try:
        yield ctx
    finally:
        ctx[CTX_KEY] = wc
        await shutdown(ctx)
        await redis.aclose()


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_worker_metrics_after_a_backfill(
    worker_ctx: dict[str, Any], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    succeeded = {"kind": "backfill", "status": "succeeded"}
    list_200 = {"endpoint": "/athlete/activities", "status": "200"}
    before_jobs = _sample("sync_jobs_total", succeeded)
    before_calls = _sample("strava_requests_total", list_200)

    assert await backfill({**worker_ctx, "job_id": "backfill:1"}, athlete_id) == "succeeded"

    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://127.0.0.1:{worker_ctx['metrics_port']}/metrics")
    assert response.status_code == 200
    scraped = {
        line.rsplit(" ", 1)[0]: float(line.rsplit(" ", 1)[1])
        for line in response.text.splitlines()
        if line and not line.startswith("#")
    }
    jobs_key = 'sync_jobs_total{kind="backfill",status="succeeded"}'
    calls_key = 'strava_requests_total{endpoint="/athlete/activities",status="200"}'
    assert scraped[jobs_key] == before_jobs + 1
    assert scraped[calls_key] >= before_calls + 2  # 250 activities = 2 pages (+ end)
    assert scraped['strava_request_duration_seconds_count{endpoint="/athlete/activities"}'] > 0


class Paused:
    async def list_activities(self, athlete_id: int, **_: Any) -> list[StravaActivity]:
        structlog.get_logger("test").info("inside_job")
        raise RateLimited(reset_at=datetime(2030, 1, 1, tzinfo=UTC))


async def test_log_lines_inside_a_job_carry_job_id(
    worker_ctx: dict[str, Any], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    wc: WorkerContext = worker_ctx[CTX_KEY]
    ctx = {**worker_ctx, CTX_KEY: dataclasses.replace(wc, strava=Paused()), "job_id": "backfill:9"}

    captured = structlog.testing.LogCapture()
    old = structlog.get_config()
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, captured])
    try:
        with pytest.raises(Exception, match="Retry"):  # arq.Retry: deferred to the reset
            await backfill(ctx, athlete_id)
        structlog.get_logger("test").info("after_job")
    finally:
        structlog.configure(**old)

    in_job = [e for e in captured.entries if e["event"] in {"inside_job", "backfill_paused"}]
    assert len(in_job) == 2
    for entry in in_job:
        assert entry["job_id"] == "backfill:9"
        assert entry["job_name"] == "backfill"
        assert entry["athlete_id"] == athlete_id
    (after,) = [e for e in captured.entries if e["event"] == "after_job"]
    assert "job_id" not in after  # the binding ends with the job
