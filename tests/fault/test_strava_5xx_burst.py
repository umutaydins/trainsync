"""Failure mode: Strava 5xx burst → retries → circuit opens → jobs delayed, reads unaffected."""

from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.fault.helpers import LIST, ManualClock, count_activities, fake_calls, metric
from tests.support.factories import create_athlete, strava_activity
from tests.support.strava import fake_backed_client
from trainsync.core.settings import Settings
from trainsync.db.models import SyncRun
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.strava.breaker import BreakerState
from trainsync.strava.budget import UnlimitedBudget
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import SyncDeps

PER_PAGE = 20


async def test_5xx_burst_opens_circuit_delays_jobs_and_reads_keep_working(
    sessionmaker: async_sessionmaker[AsyncSession],
    api: httpx.AsyncClient,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    async with sessionmaker.begin() as session:  # data synced before the outage
        await ActivityRepository(session).upsert_many(athlete_id, [strava_activity(1)])
    clock = ManualClock()
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"], clock=clock
    )
    deps = SyncDeps(sessionmaker, strava, UnlimitedBudget(), clock)
    threshold = integration_settings.strava_breaker_failure_threshold
    retries_before = metric("strava_retries_total")
    fake_strava.update_config({"error_rate": 1.0})

    # The outage: every run is paused (never failed) until the breaker opens.
    for _ in range(threshold):
        outcome = await run_backfill(deps, athlete_id, per_page=PER_PAGE)
        assert outcome.status == "paused"
        clock.advance(timedelta(seconds=1))  # job deferral, well inside the cooldown
    assert strava.breaker_state is BreakerState.OPEN
    assert metric("strava_circuit_state") == 2
    errors = sum(fake_calls(fake_strava, LIST, s) for s in ("500", "502", "503"))
    assert errors == threshold * 4  # 4 attempts per call, then stop
    assert metric("strava_retries_total") - retries_before == threshold * 3

    # While open: jobs are delayed without sending anything; reads are served from our DB.
    for _ in range(3):
        outcome = await run_backfill(deps, athlete_id, per_page=PER_PAGE)
        assert outcome.status == "paused"
        assert outcome.resume_at is not None
        assert outcome.resume_at > clock.now
    assert fake_calls(fake_strava, LIST) == errors
    response = await api.get("/v1/activities", headers={"X-API-Key": "test-api-key"})
    assert response.status_code == 200
    assert [a["id"] for a in response.json()["items"]] == [1]

    # Recovery: after the cooldown one probe succeeds and the backfill completes.
    fake_strava.update_config({"error_rate": 0.0})
    clock.advance(timedelta(seconds=integration_settings.strava_breaker_cooldown_s))
    outcome = await run_backfill(deps, athlete_id, per_page=PER_PAGE)
    assert outcome.status == "succeeded"
    assert strava.breaker_state is BreakerState.CLOSED
    assert metric("strava_circuit_state") == 0
    assert await count_activities(sessionmaker) == len(fake_strava.activities) + 1
    async with sessionmaker() as session:
        statuses = (await session.scalars(select(SyncRun.status))).all()
    assert list(statuses) == ["succeeded"]  # one run, paused and resumed, never failed
