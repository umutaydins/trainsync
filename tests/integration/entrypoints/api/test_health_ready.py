from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from asgi_lifespan import LifespanManager

from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app

pytestmark = pytest.mark.integration

# Nothing listens on port 1: connections are refused immediately.
UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"
UNREACHABLE_PG = "postgresql+asyncpg://nobody:hunter2@127.0.0.1:1/nope"


@asynccontextmanager
async def _client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_ready_when_db_and_redis_up(integration_settings: Settings) -> None:
    async with _client(integration_settings) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


async def test_not_ready_when_redis_unreachable(integration_settings: Settings) -> None:
    settings = integration_settings.model_copy(update={"redis_url": UNREACHABLE_REDIS})
    async with _client(settings) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "ok", "redis": "error"}


async def test_not_ready_when_db_unreachable_and_no_leak(integration_settings: Settings) -> None:
    settings = integration_settings.model_copy(update={"database_url": UNREACHABLE_PG})
    async with _client(settings) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "error", "redis": "ok"}
    assert "hunter2" not in response.text
    assert "127.0.0.1" not in response.text
