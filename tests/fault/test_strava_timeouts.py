"""Failure mode: Strava timeouts (fake latency > read timeout) → retries → circuit opens.

Uses a real fake_strava server, because httpx timeouts don't apply to in-process ASGI calls.
The read timeout is shortened to 0.2 s so the suite stays fast; the behaviour is the same as
with the production 10 s.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import fake_strava_login
from tests.fault.helpers import ManualClock, count_activities, metric
from tests.support.factories import create_athlete
from tests.support.fake_server import run_fake_strava
from tests.support.strava import StubTokens
from trainsync.core.settings import Settings
from trainsync.integrations.strava.breaker import BreakerState
from trainsync.integrations.strava.budget import UnlimitedBudget
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.sync.backfill import run_backfill
from trainsync.modules.sync.context import SyncDeps

LATENCY_MS = 600
READ_TIMEOUT_S = 0.2
ACTIVITIES = 60


@pytest.fixture
def server_url() -> Iterator[str]:
    with run_fake_strava(
        seed_activities=ACTIVITIES, rate_limit_15min=100_000, rate_limit_daily=1_000_000
    ) as url:
        yield url


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    timeout = httpx.Timeout(connect=1.0, read=READ_TIMEOUT_S, write=1.0, pool=1.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        yield client


async def _no_sleep(_: float) -> None:
    return None


async def test_timeouts_open_the_circuit_and_recovery_completes_the_backfill(
    server_url: str,
    http: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
) -> None:
    async with httpx.AsyncClient(base_url=server_url) as control:
        token = await fake_strava_login(control)
        await control.post("/_control/config", json={"latency_ms": LATENCY_MS})
        clock = ManualClock()
        strava = StravaClient(
            http,
            integration_settings.model_copy(
                update={
                    "strava_api_base_url": f"{server_url}/api/v3",
                    "strava_oauth_base_url": f"{server_url}/oauth",
                }
            ),
            StubTokens(token=token["access_token"], refreshed=token["access_token"]),
            clock=clock,
            sleep=_no_sleep,
        )
        athlete_id = await create_athlete(sessionmaker, token["athlete"]["id"])
        deps = SyncDeps(sessionmaker, strava, UnlimitedBudget(), clock)
        threshold = integration_settings.strava_breaker_failure_threshold
        labels = {"endpoint": "/athlete/activities", "status": "error"}
        errors_before = metric("strava_requests_total", **labels)

        for _ in range(threshold):
            assert (await run_backfill(deps, athlete_id, per_page=50)).status == "paused"
        assert strava.breaker_state is BreakerState.OPEN
        # Bounded: 4 timed-out attempts per call, nothing more once open.
        assert metric("strava_requests_total", **labels) - errors_before == threshold * 4
        assert (await run_backfill(deps, athlete_id, per_page=50)).status == "paused"
        assert metric("strava_requests_total", **labels) - errors_before == threshold * 4

        await control.post("/_control/config", json={"latency_ms": 0})
        clock.advance(timedelta(seconds=integration_settings.strava_breaker_cooldown_s))
        assert (await run_backfill(deps, athlete_id, per_page=50)).status == "succeeded"
        assert strava.breaker_state is BreakerState.CLOSED
        assert await count_activities(sessionmaker) == ACTIVITIES
