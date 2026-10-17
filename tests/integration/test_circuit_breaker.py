"""P2.5: a flaky Strava opens the circuit, sync jobs are deferred (never failed), and once Strava
recovers the backfill finishes with every activity stored exactly once."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from arq import Retry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.conftest import FAKE_STRAVA_BASE_URL
from tests.support.factories import create_athlete
from tests.support.strava import StubTokens
from trainsync.core.settings import Settings
from trainsync.db.models import Activity, SyncRun
from trainsync.strava.breaker import BreakerState
from trainsync.strava.budget import UnlimitedBudget
from trainsync.strava.client import StravaClient
from trainsync.strava.retry import RetryPolicy
from trainsync.sync.backfill import backfill, run_backfill
from trainsync.sync.common import retry_after
from trainsync.sync.context import CTX_KEY, SyncDeps

NOW = datetime(2026, 10, 17, 12, 7, tzinfo=UTC)
LIST_ENDPOINT = "GET /api/v3/athlete/activities"
MAX_JOB_RUNS = 500
# Small pages: ~100 calls for the history, so the breaker sees enough of the 50% error rate.
PER_PAGE = 10


@dataclass
class ManualClock:
    now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=1000, rate_limit_15min=10_000, rate_limit_daily=100_000)


async def _no_sleep(_: float) -> None:
    return None


def _list_calls(fake: FakeStravaState) -> int:
    return sum(fake.stats_json()["requests"].get(LIST_ENDPOINT, {}).values())


async def _set_error_rate(client: httpx.AsyncClient, rate: float) -> None:
    response = await client.post("/_control/config", json={"error_rate": rate})
    response.raise_for_status()


async def _run_status(sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    async with sessionmaker() as session:
        (status,) = (await session.scalars(select(SyncRun.status))).all()
        return status


async def test_flaky_strava_opens_circuit_defers_jobs_and_recovers(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    clock = ManualClock()
    token = fake_strava_token["access_token"]
    strava = StravaClient(
        fake_strava_client,
        integration_settings.model_copy(
            update={
                "strava_api_base_url": f"{FAKE_STRAVA_BASE_URL}/api/v3",
                "strava_oauth_base_url": f"{FAKE_STRAVA_BASE_URL}/oauth",
            }
        ),
        StubTokens(token=token, refreshed=token),
        # One attempt per call: with four, a 50% error rate fails a call only 6% of the time
        # and five in a row would almost never happen.
        policy=RetryPolicy(max_attempts=1),
        clock=clock,
        sleep=_no_sleep,
    )
    deps = SyncDeps(sessionmaker, strava, UnlimitedBudget(), clock)
    ctx = {CTX_KEY: SimpleNamespace(sync_deps=lambda: deps, clock=clock)}
    athlete_id = await create_athlete(sessionmaker)
    await _set_error_rate(fake_strava_client, 0.5)

    opened = False
    deferrals = 0
    for _ in range(MAX_JOB_RUNS):
        # What the `backfill` job does, with small pages; any exception fails the test.
        outcome = await run_backfill(deps, athlete_id, per_page=PER_PAGE)
        retry = retry_after(outcome.resume_at, clock())
        if retry is None:
            break
        deferrals += 1
        assert outcome.status == "paused"
        assert await _run_status(sessionmaker) == "paused"
        if not opened and strava.breaker_state is BreakerState.OPEN:
            opened = True
            await _assert_open_circuit_defers_without_calling(
                ctx, athlete_id, fake_strava, sessionmaker, integration_settings
            )
            await _set_error_rate(fake_strava_client, 0.0)
        assert retry.defer_score is not None
        clock.now += timedelta(milliseconds=retry.defer_score)
    else:
        pytest.fail(f"backfill did not finish within {MAX_JOB_RUNS} job runs")

    assert opened, "the circuit never opened at a 50% error rate"
    assert outcome.status == "succeeded"
    assert deferrals > 1
    assert strava.breaker_state is BreakerState.CLOSED
    async with sessionmaker() as session:
        stored = (await session.scalars(select(Activity.strava_activity_id))).all()
        assert await session.scalar(select(func.count()).select_from(Activity)) == 1000
    assert sorted(stored) == sorted(fake_strava.activities)


async def _assert_open_circuit_defers_without_calling(
    ctx: dict[str, Any],
    athlete_id: int,
    fake_strava: FakeStravaState,
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    calls = _list_calls(fake_strava)
    with pytest.raises(Retry) as exc_info:
        await backfill(ctx, athlete_id)
    assert _list_calls(fake_strava) == calls
    assert await _run_status(sessionmaker) == "paused"
    defer_ms = exc_info.value.defer_score
    assert defer_ms is not None
    cooldown = settings.strava_breaker_cooldown_s
    assert cooldown < defer_ms / 1000 <= cooldown + 2
