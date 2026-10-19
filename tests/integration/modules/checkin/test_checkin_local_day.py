"""Job 6: the check-in views default to the signed-in user's local day, not the server's zone."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import create_user, signed_in
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app

# 23:30 UTC on 18 Oct is already 19 Oct in Auckland (UTC+13) and still 18 Oct in UTC.
NOW = datetime(2026, 10, 18, 23, 30, tzinfo=UTC)


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


async def test_the_default_range_ends_on_the_user_s_today(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    kiwi = await create_user(sessionmaker, "kiwi@example.com", timezone="Pacific/Auckland")
    utc = await create_user(sessionmaker, "utc@example.com", timezone="UTC")
    for account, today in ((kiwi, "2026-10-19"), (utc, "2026-10-18")):
        async with signed_in(app, account) as api:
            listed = (await api.get("/v1/checkins")).json()
            summary = (await api.get("/v1/checkins/summary")).json()
        assert listed["to"] == today
        assert summary["to"] == today
