"""A failed run's error reaches people as a code; the technical text only the owner sees."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import API_KEY, OWNER_ID, client, create_user, signed_in
from tests.support.factories import create_athlete
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.integrations.strava.errors import StravaAuthError
from trainsync.modules.sync.common import short_error
from trainsync.modules.sync.models import SyncKind, SyncStatus
from trainsync.modules.sync.repository import SyncRunRepository

NOW = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)
ERROR = short_error(StravaAuthError("refresh token rejected by Strava"))


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


async def _failed_backfill(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> None:
    athlete_id = await create_athlete(sessionmaker, 5000 + user_id, user_id=user_id)
    async with sessionmaker.begin() as session:
        runs = SyncRunRepository(session)
        run = await runs.create(athlete_id, SyncKind.BACKFILL, {"before": None}, NOW)
        await runs.set_status(run.id, SyncStatus.FAILED, NOW, error=ERROR)


def _backfill(response: httpx.Response) -> dict[str, object]:
    assert response.status_code == 200, response.text
    (athlete,) = response.json()["athletes"]
    backfill: dict[str, object] = athlete["backfill"]
    return backfill


async def test_a_member_gets_the_code_without_the_technical_text(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    member = await create_user(sessionmaker, "member@example.com")
    await _failed_backfill(sessionmaker, member.id)
    async with signed_in(app, member) as api:
        backfill = _backfill(await api.get("/v1/sync/status"))
    assert (backfill["status"], backfill["error_code"], backfill["error"]) == (
        "failed",
        "strava_auth",
        None,
    )


async def test_the_owner_also_gets_the_technical_text(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _failed_backfill(sessionmaker, OWNER_ID)
    async with client(app, **{"X-API-Key": API_KEY}) as api:
        backfill = _backfill(await api.get("/v1/sync/status"))
    assert (backfill["error_code"], backfill["error"]) == ("strava_auth", ERROR)
