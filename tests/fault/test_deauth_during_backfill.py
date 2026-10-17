"""Failure mode: user revokes access → deauth event → tokens and data removed, even while a
backfill is running.

The backfill fetches a page; before it can store it, the athlete revokes access in Strava, the
webhook arrives and is processed. The page in flight must not bring any data back, and the
backfill must stop instead of fetching more.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.fault.conftest import API_URL
from tests.fault.helpers import LIST, count_activities, drain_webhooks, fake_calls
from tests.support import fake_webhooks
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.clock import utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.settings import Settings
from trainsync.db.models import Athlete, OAuthToken, SyncRun
from trainsync.db.repositories.tokens import SqlTokenStore, Tokens
from trainsync.strava.budget import UnlimitedBudget
from trainsync.strava.models import StravaActivity
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import ActivitySource, SyncDeps
from trainsync.sync.webhooks import WebhookDeps

TARGET = f"{API_URL}/webhooks/strava"


@dataclass
class HoldThirdPage:
    """Fetches normally, but holds the third page until released (the page is in flight)."""

    inner: ActivitySource
    calls: int = 0
    holding: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def list_activities(self, athlete_id: int, **kwargs: Any) -> list[StravaActivity]:
        page = await self.inner.list_activities(athlete_id, **kwargs)
        self.calls += 1
        if self.calls == 3:
            self.holding.set()
            await self.release.wait()
        return page


async def test_deauthorization_mid_backfill_leaves_nothing_behind(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    await SqlTokenStore(sessionmaker, TokenCipher.from_settings(integration_settings)).save(
        athlete_id,
        Tokens(
            fake_strava_token["access_token"],
            fake_strava_token["refresh_token"],
            datetime.now(UTC) + timedelta(hours=5),
            "read,activity:read_all",
        ),
    )
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    source = HoldThirdPage(strava)
    backfill = asyncio.create_task(
        run_backfill(
            SyncDeps(sessionmaker, source, UnlimitedBudget(), utc_now), athlete_id, per_page=50
        )
    )
    await asyncio.wait_for(source.holding.wait(), timeout=10)
    assert await count_activities(sessionmaker) > 50  # two pages stored so far

    scenario = await fake_webhooks.deauthorize(fake_strava_client, TARGET)
    assert scenario.report.delivered == 1
    hooks = WebhookDeps(sessionmaker, strava, utc_now)
    assert await drain_webhooks(hooks, sessionmaker) == ["deauthorized"]
    lists_at_deauth = fake_calls(fake_strava, LIST)

    source.release.set()
    outcome = await asyncio.wait_for(backfill, timeout=10)
    assert outcome.status == "skipped"

    assert await count_activities(sessionmaker) == 0
    assert fake_calls(fake_strava, LIST) == lists_at_deauth  # stopped: no further pages
    async with sessionmaker() as session:
        athlete = await session.get(Athlete, athlete_id)
        assert athlete is not None
        assert athlete.active is False
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 0
        run = await session.scalar(select(SyncRun))
        assert run is not None
        assert (run.status, run.pages) == ("failed", 2)
        assert run.error == "athlete deauthorized during sync"
