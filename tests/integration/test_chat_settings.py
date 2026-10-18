"""P6.12: `/v1/chats/{chat_id}/settings` stores the chat's language in Postgres (ADR 0031): null
until chosen, idempotent, survives a restart of the API."""

from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.settings import Settings
from trainsync.db.models import ChatSetting
from trainsync.main import create_app

pytestmark = pytest.mark.integration

KEY = {"X-API-Key": "test-api-key"}
URL = "/v1/chats/4242/settings"


Api = Callable[[], AsyncIterator[httpx.AsyncClient]]


@pytest.fixture
def api_factory(integration_settings: Settings) -> Api:
    """Each call starts the API afresh (a new process, as far as the database is concerned)."""

    async def start() -> AsyncIterator[httpx.AsyncClient]:
        app = create_app(integration_settings)
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://api", headers=KEY
            ) as client:
                yield client

    return start


async def test_language_is_null_until_chosen_then_stored(
    api_factory: Api, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async for api in api_factory():
        assert (await api.get(URL)).json() == {"chat_id": 4242, "lang": None}
        for _ in range(2):  # idempotent
            response = await api.put(URL, json={"lang": "tr"})
            assert response.status_code == 200
            assert response.json() == {"chat_id": 4242, "lang": "tr"}
        assert (await api.put(URL, json={"lang": "de"})).status_code == 422
        assert (await api.get(URL, headers={"X-API-Key": "wrong"})).status_code == 401
    async for api in api_factory():  # a new process: the database still has it
        assert (await api.get(URL)).json()["lang"] == "tr"
        await api.put(URL, json={"lang": "en"})
        assert (await api.get(URL)).json()["lang"] == "en"
        assert (await api.get("/v1/chats/1/settings")).json()["lang"] is None
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(ChatSetting)) == 1
