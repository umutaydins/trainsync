"""Container fixtures (pytest plugin, registered in tests/conftest.py): real Postgres 16 and
Redis 7 via testcontainers.

Containers and the `alembic upgrade head` run once per session and only when a test asks for
them. `clean_state` empties tables and Redis; the integration and fault suites use it autouse.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from tests.conftest import make_settings
from tests.support.accounts import OWNER_EMAIL
from trainsync.core.security import UNUSABLE_HASH
from trainsync.core.settings import Settings
from trainsync.modules.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


# The exercise library (migration 0005) stays; `users` is emptied with DELETE, because a
# TRUNCATE ... CASCADE of it would also truncate `exercises` (custom ones reference a user).
KEPT = frozenset({"exercises", "users"})


async def _reset_state(pg_url: str, redis_url: str) -> None:
    engine = create_async_engine(pg_url, poolclass=NullPool)
    try:
        tables = ", ".join(
            table.name for table in Base.metadata.sorted_tables if table.name not in KEPT
        )
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            await conn.execute(text("DELETE FROM exercises WHERE is_custom"))
            await conn.execute(text("DELETE FROM users"))
            await conn.execute(text("ALTER SEQUENCE users_id_seq RESTART"))
            # The owner every API-key request acts as (ADR 0034); id 1 after the restart.
            await conn.execute(
                text(
                    "INSERT INTO users (email, password_hash, display_name, role, timezone)"
                    " VALUES (:email, :hash, 'Owner', 'owner', 'UTC')"
                ),
                {"email": OWNER_EMAIL, "hash": UNUSABLE_HASH},
            )
    finally:
        await engine.dispose()
    redis = Redis.from_url(redis_url)
    try:
        await redis.flushdb()
    finally:
        await redis.aclose()


@pytest.fixture
def clean_state(pg_url: str, redis_url: str) -> None:
    """Truncate all tables and flush Redis before each integration test.

    Sync on purpose: it runs outside the test's event loop, so sync tests that drive Alembic
    (which calls `asyncio.run`) can use it too.
    """
    asyncio.run(_reset_state(pg_url, redis_url))


@pytest.fixture
def integration_settings(pg_url: str, redis_url: str) -> Settings:
    # The test key is also a service key, so the bot's chat lookups work against the real API.
    return make_settings(database_url=pg_url, redis_url=redis_url, service_api_keys="test-api-key")


@pytest.fixture
async def engine(pg_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(pg_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    yield client
    await client.aclose()
