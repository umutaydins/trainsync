import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from arq import Retry
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.settings import Settings
from trainsync.db.models import Activity, SyncRun
from trainsync.db.repositories.athletes import AthleteRepository
from trainsync.strava.budget import Allowance, Priority, UnlimitedBudget
from trainsync.strava.errors import RateLimited, StravaAuthError, StravaUnavailable
from trainsync.strava.models import StravaActivity
from trainsync.sync.backfill import STALE_AFTER, backfill, run_backfill
from trainsync.sync.common import UNAVAILABLE_DEFER
from trainsync.sync.context import CTX_KEY, ActivitySource, SyncDeps

NOW = datetime(2026, 10, 17, 12, 7, tzinfo=UTC)
LIST_ENDPOINT = "GET /api/v3/athlete/activities"


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=1000, rate_limit_15min=10_000, rate_limit_daily=100_000)


@pytest.fixture
def strava(
    fake_strava_client: httpx.AsyncClient,
    integration_settings: Settings,
    fake_strava_token: dict[str, Any],
) -> ActivitySource:
    return fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )


def deps(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    now: datetime = NOW,
) -> SyncDeps:
    return SyncDeps(sessionmaker, strava, UnlimitedBudget(), lambda: now)


async def _count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(Activity)) or 0


async def _runs(sessionmaker: async_sessionmaker[AsyncSession]) -> list[SyncRun]:
    async with sessionmaker() as session:
        return list((await session.scalars(select(SyncRun).order_by(SyncRun.id))).all())


def _list_calls(fake: FakeStravaState) -> int:
    return sum(fake.stats_json()["requests"].get(LIST_ENDPOINT, {}).values())


async def test_backfill_stores_everything_once(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    outcome = await run_backfill(deps(sessionmaker, strava), athlete_id)
    assert outcome.status == "succeeded"
    assert await _count(sessionmaker) == 1000
    (run,) = await _runs(sessionmaker)
    assert (run.kind, run.status, run.upserted) == ("backfill", "succeeded", 1000)
    assert run.finished_at is not None

    again = await run_backfill(deps(sessionmaker, strava), athlete_id)
    assert again.status == "succeeded"
    runs = await _runs(sessionmaker)
    assert [r.upserted for r in runs] == [1000, 0]
    assert await _count(sessionmaker) == 1000


@dataclass
class CrashAfter:
    """Forwards to the real client; the call after `pages` hangs (the worker 'dies' there)."""

    inner: ActivitySource
    pages: int
    calls: int = 0
    reached: asyncio.Event = field(default_factory=asyncio.Event)

    async def list_activities(self, athlete_id: int, **kwargs: Any) -> list[StravaActivity]:
        self.calls += 1
        if self.calls > self.pages:
            self.reached.set()
            await asyncio.Event().wait()
        return await self.inner.list_activities(athlete_id, **kwargs)


async def _wipe(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker.begin() as session:
        await session.execute(Activity.__table__.delete())
        await session.execute(SyncRun.__table__.delete())


async def test_cancelled_backfill_resumes_from_cursor(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    fake_strava: FakeStravaState,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    # Pages a clean, uninterrupted backfill of the same data needs.
    await run_backfill(deps(sessionmaker, strava), athlete_id)
    pages_needed = _list_calls(fake_strava)
    await _wipe(sessionmaker)

    start = _list_calls(fake_strava)
    crashing = CrashAfter(strava, pages=3)
    task = asyncio.create_task(run_backfill(deps(sessionmaker, crashing), athlete_id))
    await asyncio.wait_for(crashing.reached.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (run,) = await _runs(sessionmaker)
    assert (run.status, run.pages) == ("paused", 3)
    assert 0 < await _count(sessionmaker) < 1000

    outcome = await run_backfill(deps(sessionmaker, strava), athlete_id)
    assert outcome.status == "succeeded"
    assert outcome.run_id == run.id  # resumed the same run, not a new one
    assert await _count(sessionmaker) == 1000
    fetched = _list_calls(fake_strava) - start
    assert pages_needed <= fetched <= pages_needed + 1


async def test_stale_running_run_is_taken_over_live_one_is_not(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource
) -> None:
    """A hard crash leaves the run `running`; it is resumed once its heartbeat is stale."""
    athlete_id = await create_athlete(sessionmaker)
    crashing = CrashAfter(strava, pages=2)
    task = asyncio.create_task(run_backfill(deps(sessionmaker, crashing), athlete_id))
    await asyncio.wait_for(crashing.reached.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with sessionmaker.begin() as session:  # simulate SIGKILL: no chance to pause
        await session.execute(update(SyncRun).values(status="running"))

    live = await run_backfill(
        deps(sessionmaker, strava, now=NOW + timedelta(minutes=1)), athlete_id
    )
    assert live.status == "already_running"
    later = NOW + STALE_AFTER + timedelta(seconds=1)
    resumed = await run_backfill(deps(sessionmaker, strava, now=later), athlete_id)
    assert resumed.status == "succeeded"
    assert await _count(sessionmaker) == 1000


async def test_activities_sharing_start_date_across_page_boundary(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    fake_strava: FakeStravaState,
) -> None:
    for activity_id in list(fake_strava.activities):
        del fake_strava.activities[activity_id]
    tie = datetime(2025, 6, 1, 7, 0, tzinfo=UTC)
    # With per_page=3 the first page ends in the middle of the two activities at `tie`.
    dates = [
        tie + timedelta(hours=2),
        tie + timedelta(hours=1),
        tie,
        tie,
        tie - timedelta(days=1),
        tie - timedelta(days=2),
    ]
    for n, start in enumerate(dates, start=1):
        fake_strava.apply_change(
            "create", athlete_id=None, activity_id=n, fields={"start_date": start.isoformat()}
        )
    athlete_id = await create_athlete(sessionmaker)
    outcome = await run_backfill(deps(sessionmaker, strava), athlete_id, per_page=3)
    assert outcome.status == "succeeded"
    async with sessionmaker() as session:
        stored = set((await session.scalars(select(Activity.strava_activity_id))).all())
    assert stored == set(range(1, 7))


@dataclass
class Scripted:
    """Raises the given exception on the first call."""

    error: Exception

    async def list_activities(self, athlete_id: int, **kwargs: Any) -> list[StravaActivity]:
        raise self.error


async def test_rate_limited_pauses_and_job_is_deferred_to_reset(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    reset_at = datetime(2026, 10, 17, 12, 15, tzinfo=UTC)
    stub = Scripted(RateLimited(reset_at=reset_at))
    context = SimpleNamespace(sync_deps=lambda: deps(sessionmaker, stub), clock=lambda: NOW)
    with pytest.raises(Retry) as exc_info:
        await backfill({CTX_KEY: context}, athlete_id)
    defer_ms = exc_info.value.defer_score
    assert defer_ms is not None
    assert abs(defer_ms / 1000 - (reset_at - NOW).total_seconds()) <= 2
    (run,) = await _runs(sessionmaker)
    assert run.status == "paused"


async def test_strava_unavailable_pauses_instead_of_failing(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    stub = Scripted(StravaUnavailable("/athlete/activities: 503"))
    outcome = await run_backfill(deps(sessionmaker, stub), athlete_id)
    assert outcome.status == "paused"
    assert outcome.resume_at == NOW + UNAVAILABLE_DEFER
    (run,) = await _runs(sessionmaker)
    assert run.status == "paused"


class DenyLow:
    async def allow(self, priority: Priority) -> Allowance:
        return Allowance(priority == "high", NOW + timedelta(minutes=8))


async def test_budget_denial_pauses_before_calling_strava(
    sessionmaker: async_sessionmaker[AsyncSession],
    strava: ActivitySource,
    fake_strava: FakeStravaState,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    before = _list_calls(fake_strava)
    outcome = await run_backfill(SyncDeps(sessionmaker, strava, DenyLow(), lambda: NOW), athlete_id)
    assert outcome.status == "paused"
    assert outcome.resume_at == NOW + timedelta(minutes=8)
    assert _list_calls(fake_strava) == before


async def test_auth_error_fails_run_without_raising(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    outcome = await run_backfill(
        deps(sessionmaker, Scripted(StravaAuthError("revoked"))), athlete_id
    )
    assert outcome.status == "failed"
    (run,) = await _runs(sessionmaker)
    assert run.status == "failed"
    assert run.error is not None
    assert "StravaAuthError" in run.error


async def test_unexpected_error_fails_run_and_reraises(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    with pytest.raises(ValueError, match="boom"):
        await run_backfill(deps(sessionmaker, Scripted(ValueError("boom"))), athlete_id)
    (run,) = await _runs(sessionmaker)
    assert (run.status, run.error) == ("failed", "ValueError: boom")


async def test_inactive_athlete_is_skipped(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource
) -> None:
    athlete_id = await create_athlete(sessionmaker, active=False)
    assert (await run_backfill(deps(sessionmaker, strava), athlete_id)).status == "skipped"
    assert await _runs(sessionmaker) == []


@dataclass
class DeauthorizeDuringFetch:
    """The athlete revokes access while a page is in flight."""

    inner: ActivitySource
    sessionmaker: async_sessionmaker[AsyncSession]

    async def list_activities(self, athlete_id: int, **kwargs: Any) -> list[StravaActivity]:
        page = await self.inner.list_activities(athlete_id, **kwargs)
        async with self.sessionmaker.begin() as session:
            await AthleteRepository(session).deauthorize(athlete_id)
        return page


async def test_deauthorization_mid_backfill_writes_nothing_back(
    sessionmaker: async_sessionmaker[AsyncSession], strava: ActivitySource
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    source = DeauthorizeDuringFetch(strava, sessionmaker)
    outcome = await run_backfill(deps(sessionmaker, source), athlete_id)
    assert outcome.status == "skipped"
    assert await _count(sessionmaker) == 0
    (run,) = await _runs(sessionmaker)
    assert (run.status, run.pages, run.error) == ("failed", 0, "athlete deauthorized during sync")
