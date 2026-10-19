"""Regression (P6.11 bug, 2026-10-18): the assistant said "no synced data (last_synced_at
empty)". A completed backfill must set `last_synced_at` in every response the assistant reads,
and before any sync the sync status must say why it is empty (no athlete, or a run going on)."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.config import FakeStravaConfig
from tests.support.factories import create_athlete
from tests.support.messages import NEUTRAL_EN
from tests.support.strava import fake_backed_client
from trainsync.core.clock import utc_now
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.integrations.strava.budget import UnlimitedBudget
from trainsync.modules.chat.assistant import Assistant
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.sync.backfill import run_backfill
from trainsync.modules.sync.context import SyncDeps

pytestmark = pytest.mark.integration

KEY = "test-api-key"
TOOL_CALLS = [
    ("get_summary", {"from": "2021-01-01", "to": "2030-12-31", "sport_type": None}),
    ("get_weekly", {"from": "2026-01-01", "to": "2026-12-31", "sport_type": None}),
    ("list_activities", {"from": None, "to": None, "sport_type": None, "limit": 1}),
    ("get_sync_status", {}),
]


@pytest.fixture
def fake_strava_config(request: pytest.FixtureRequest) -> FakeStravaConfig:
    return FakeStravaConfig(seed_activities=getattr(request, "param", 40))


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def tools(app: FastAPI) -> AsyncIterator[Assistant]:
    """The assistant's own tool code, reading the API in-process (no model needed)."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
        api = ReadApi(http, "http://api", SecretStr(KEY))
        yield Assistant(None, api, None, utc_now, NEUTRAL_EN)  # type: ignore[arg-type]


async def backfill(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava_client: httpx.AsyncClient,
    settings: Settings,
    token: dict[str, Any],
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    strava = fake_backed_client(fake_strava_client, settings, token["access_token"])
    outcome = await run_backfill(
        SyncDeps(sessionmaker, strava, UnlimitedBudget(), utc_now), athlete_id
    )
    assert outcome.status == "succeeded"


async def test_a_completed_backfill_sets_last_synced_at_everywhere_the_assistant_reads(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava_client: httpx.AsyncClient,
    integration_settings: Settings,
    fake_strava_token: dict[str, Any],
    tools: Assistant,
) -> None:
    await backfill(sessionmaker, fake_strava_client, integration_settings, fake_strava_token)
    for name, args in TOOL_CALLS:
        result = await tools.execute(name, args)
        assert '"last_synced_at":null' not in result.replace(" ", ""), name
        assert '"last_synced_at":"' in result.replace(" ", ""), name


@pytest.mark.parametrize("fake_strava_config", [0], indirect=True)
async def test_an_athlete_without_activities_still_gets_last_synced_at(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava_client: httpx.AsyncClient,
    integration_settings: Settings,
    fake_strava_token: dict[str, Any],
    tools: Assistant,
) -> None:
    await backfill(sessionmaker, fake_strava_client, integration_settings, fake_strava_token)
    listed = await tools.execute(*TOOL_CALLS[2])
    assert '"items":[]' in listed.replace(" ", "")  # really no activities
    status = await tools.execute("get_sync_status", {})
    assert '"last_synced_at":"' in status.replace(" ", "")


async def test_before_any_sync_the_status_explains_the_empty_value(tools: Assistant) -> None:
    """No athlete yet: the assistant sees an empty athlete list next to the null (and the
    prompt tells it to say "not connected", not "no data")."""
    status = await tools.execute("get_sync_status", {})
    compact = status.replace(" ", "")
    assert '"last_synced_at":null' in compact
    assert '"athletes":[]' in compact
