from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from arq import Retry, create_pool
from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.settings import Settings
from trainsync.db.models import Activity, SyncRun
from trainsync.strava.budget import UnlimitedBudget
from trainsync.strava.errors import RateLimited
from trainsync.strava.models import StravaActivity
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import CTX_KEY, ActivitySource, SyncDeps
from trainsync.sync.incremental import (
    enqueue_incremental_jobs,
    incremental_sync,
    run_incremental,
    window_key,
)
from trainsync.sync.queue import redis_settings

NOW = datetime(2026, 10, 18, 12, 40, tzinfo=UTC)


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=50)


@pytest.fixture
def strava(
    fake_strava_client: httpx.AsyncClient,
    integration_settings: Settings,
    fake_strava_token: dict[str, Any],
) -> ActivitySource:
    return fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )


@pytest.fixture
async def pool(integration_settings: Settings) -> AsyncIterator[ArqRedis]:
    redis = await create_pool(redis_settings(integration_settings))
    yield redis
    await redis.aclose()


def deps(sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource) -> SyncDeps:
    return SyncDeps(sessionmaker, strava, UnlimitedBudget(), lambda: NOW)


def newest(fake: FakeStravaState) -> datetime:
    return max(a.start_date for a in fake.activities.values())


def create(fake: FakeStravaState, activity_id: int, start: datetime, **fields: object) -> None:
    fake.apply_change(
        "create",
        athlete_id=None,
        activity_id=activity_id,
        fields={"start_date": start.isoformat(), **fields},
    )


async def _stored_ids(sessionmaker: async_sessionmaker[AsyncSession]) -> set[int]:
    async with sessionmaker() as session:
        return set((await session.scalars(select(Activity.strava_activity_id))).all())


async def _incremental_runs(sessionmaker: async_sessionmaker[AsyncSession]) -> list[SyncRun]:
    async with sessionmaker() as session:
        stmt = select(SyncRun).where(SyncRun.kind == "incremental").order_by(SyncRun.id)
        return list((await session.scalars(stmt)).all())


async def test_edit_to_activity_from_one_day_ago_is_synced(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
) -> None:
    create(fake_strava, 1, newest(fake_strava) - timedelta(days=1), name="Long Run")
    athlete_id = await create_athlete(sessionmaker)
    assert (await run_backfill(deps(sessionmaker, strava), athlete_id)).status == "succeeded"

    response = await fake_strava_client.post(
        "/_control/activities",
        json={"action": "update", "id": 1, "fields": {"name": "Long Run (edited)"}},
    )
    assert response.status_code == 200, response.text

    outcome = await run_incremental(deps(sessionmaker, strava), athlete_id)
    assert outcome.status == "succeeded"
    async with sessionmaker() as session:
        name = await session.scalar(select(Activity.name).where(Activity.strava_activity_id == 1))
    assert name == "Long Run (edited)"
    (run,) = await _incremental_runs(sessionmaker)
    assert (run.status, run.upserted) == ("succeeded", 1)
    assert run.cursor["after"] == int((newest(fake_strava) - timedelta(days=2)).timestamp())


async def test_late_upload_inside_window_is_picked_up(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    fake_strava: FakeStravaState,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    await run_backfill(deps(sessionmaker, strava), athlete_id)
    latest = newest(fake_strava)
    create(fake_strava, 2, latest - timedelta(hours=36))
    create(fake_strava, 3, latest - timedelta(days=3))
    assert (await run_incremental(deps(sessionmaker, strava), athlete_id)).status == "succeeded"
    stored = await _stored_ids(sessionmaker)
    assert 2 in stored
    assert 3 not in stored  # older than the overlap window: backfill territory


async def test_paginates_inside_window(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    fake_strava: FakeStravaState,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    await run_backfill(deps(sessionmaker, strava), athlete_id)
    latest = newest(fake_strava)
    for n in range(10, 17):
        create(fake_strava, n, latest - timedelta(hours=n))
    outcome = await run_incremental(deps(sessionmaker, strava), athlete_id, per_page=3)
    assert outcome.status == "succeeded"
    assert set(range(10, 17)) <= await _stored_ids(sessionmaker)
    (run,) = await _incremental_runs(sessionmaker)
    assert run.pages >= 3


@dataclass
class RateLimitedSource:
    async def list_activities(self, athlete_id: int, **kwargs: Any) -> list[StravaActivity]:
        raise RateLimited(reset_at=datetime(2026, 10, 18, 12, 45, tzinfo=UTC))


async def test_rate_limited_run_pauses_and_resumes_same_run(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    await run_backfill(deps(sessionmaker, strava), athlete_id)
    context = SimpleNamespace(
        sync_deps=lambda: deps(sessionmaker, RateLimitedSource()), clock=lambda: NOW
    )
    with pytest.raises(Retry):
        await incremental_sync({CTX_KEY: context}, athlete_id)
    (paused,) = await _incremental_runs(sessionmaker)
    assert paused.status == "paused"

    resumed = await run_incremental(deps(sessionmaker, strava), athlete_id)
    assert resumed.status == "succeeded"
    assert [(r.id, r.status) for r in await _incremental_runs(sessionmaker)] == [
        (paused.id, "succeeded")
    ]


async def test_without_history_a_backfill_is_enqueued_instead(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource, pool: ArqRedis
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    context = SimpleNamespace(
        sync_deps=lambda: deps(sessionmaker, strava), clock=lambda: NOW, redis=pool
    )
    assert await incremental_sync({CTX_KEY: context}, athlete_id) == "backfill_enqueued"
    assert [j.job_id for j in await pool.queued_jobs()] == [f"backfill:{athlete_id}"]
    assert await _incremental_runs(sessionmaker) == []


async def test_skipped_while_backfill_open_or_inactive(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource
) -> None:
    inactive = await create_athlete(sessionmaker, strava_id=2, active=False)
    assert (await run_incremental(deps(sessionmaker, strava), inactive)).status == "skipped"
    athlete_id = await create_athlete(sessionmaker)
    async with sessionmaker.begin() as session:
        session.add(SyncRun(athlete_id=athlete_id, kind="backfill", status="paused", cursor={}))
    assert (await run_incremental(deps(sessionmaker, strava), athlete_id)).status == "skipped"


async def test_cron_enqueues_one_job_per_active_athlete_per_window(
    sessionmaker: async_sessionmaker[AsyncSession], pool: ArqRedis
) -> None:
    done = await create_athlete(sessionmaker, strava_id=1)
    fresh = await create_athlete(sessionmaker, strava_id=2)
    await create_athlete(sessionmaker, strava_id=3, active=False)
    mid_backfill = await create_athlete(sessionmaker, strava_id=4)
    paused_backfill = await create_athlete(sessionmaker, strava_id=5)
    async with sessionmaker.begin() as session:
        session.add_all(
            [
                SyncRun(athlete_id=done, kind="backfill", status="succeeded", cursor={}),
                SyncRun(athlete_id=mid_backfill, kind="backfill", status="running", cursor={}),
                SyncRun(athlete_id=paused_backfill, kind="backfill", status="paused", cursor={}),
            ]
        )

    first = await enqueue_incremental_jobs(sessionmaker, pool, NOW)
    again = await enqueue_incremental_jobs(sessionmaker, pool, NOW + timedelta(minutes=10))
    assert first == [done, fresh]
    assert again == []  # same 12:30 window
    window = window_key(NOW)
    assert window == "202610181230"
    assert sorted(j.job_id or "" for j in await pool.queued_jobs()) == [
        f"incremental:{done}:{window}",
        f"incremental:{fresh}:{window}",
    ]

    next_window = await enqueue_incremental_jobs(sessionmaker, pool, NOW + timedelta(minutes=20))
    assert next_window == [done, fresh]
    assert len(await pool.queued_jobs()) == 4
