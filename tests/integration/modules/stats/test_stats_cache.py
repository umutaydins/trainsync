"""P8.10, ADR 0038: the statistics cache is keyed by a data version the database keeps."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import create_user, signed_in
from tests.support.stats_data import Lift, Seeder
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.stats.cache import data_version
from trainsync.modules.stats.models import VERSIONED_TABLES

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


async def _version(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    async with sessionmaker() as session:
        return await data_version(session, user_id)


async def test_every_table_the_statistics_read_has_the_trigger(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        rows = await session.execute(
            text(
                "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
                " WHERE t.tgname = 'bump_user_data_version'"
            )
        )
        assert {name for (name,) in rows} == set(VERSIONED_TABLES)


async def test_a_write_bumps_only_its_user_s_version(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    before = (await _version(sessionmaker, alice.id), await _version(sessionmaker, bob.id))
    async with sessionmaker.begin() as session:
        seed = Seeder(session, alice.id)
        await seed.workout(NOW, [Lift("bench-press", 5, 80)])
        seed.weight(date(2026, 10, 27), 70.0)
    after = (await _version(sessionmaker, alice.id), await _version(sessionmaker, bob.id))
    assert after[0] > before[0]
    assert after[1] == before[1]
    async with sessionmaker.begin() as session:
        await session.execute(text("DELETE FROM body_metrics WHERE user_id = :u"), {"u": alice.id})
    assert await _version(sessionmaker, alice.id) > after[0]


async def test_cached_until_the_data_changes(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """`all` (here since 2025, over STATS_CACHE_MIN_DAYS) is cached; a weigh-in through the API
    changes the key, so the next answer is new."""
    user = await create_user(sessionmaker, "carol@example.com")
    async with sessionmaker.begin() as session:
        Seeder(session, user.id).weight(date(2025, 1, 1), 70.0)
    async with signed_in(app, user) as api:
        first = (await api.get("/v1/stats/summary", params={"period": "all"})).json()
        keys = await redis.keys(f"stats:{user.id}:*")
        again = (await api.get("/v1/stats/summary", params={"period": "all"})).json()
        assert len(keys) == 1
        assert again == first
        put = await api.put("/v1/training/body-metrics/2026-10-27", json={"weight_kg": 69.0})
        assert put.status_code == 200, put.text
        fresh = (await api.get("/v1/stats/summary", params={"period": "all"})).json()
        short = await api.get("/v1/stats/summary", params={"period": "week"})
    assert (first["body"]["last_kg"], fresh["body"]["last_kg"]) == (70.0, 69.0)
    assert len(await redis.keys(f"stats:{user.id}:*")) == 2  # the week is never cached
    assert short.status_code == 200
