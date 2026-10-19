"""P6.12, P6.13: `/v1/chats/{chat_id}/settings` stores the chat's language (ADR 0031) and
profanity level (ADR 0032) in Postgres: null until chosen, idempotent, either field alone keeps the
other, survives a restart of the API."""

from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.chat.models import ChatSetting

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
        assert (await api.get(URL)).json() == {"chat_id": 4242, "lang": None, "profanity": None}
        for _ in range(2):  # idempotent
            response = await api.put(URL, json={"lang": "tr"})
            assert response.status_code == 200
            assert response.json() == {"chat_id": 4242, "lang": "tr", "profanity": None}
        assert (await api.put(URL, json={"lang": "de"})).status_code == 422
        assert (await api.get(URL, headers={"X-API-Key": "wrong"})).status_code == 401
    async for api in api_factory():  # a new process: the database still has it
        assert (await api.get(URL)).json()["lang"] == "tr"
        await api.put(URL, json={"lang": "en"})
        assert (await api.get(URL)).json()["lang"] == "en"
        assert (await api.get("/v1/chats/1/settings")).json()["lang"] is None
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(ChatSetting)) == 1


async def test_profanity_is_stored_next_to_the_language(
    api_factory: Api, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async for api in api_factory():
        only = await api.put("/v1/chats/7/settings", json={"profanity": "max"})
        assert only.json() == {"chat_id": 7, "lang": None, "profanity": "max"}
        both = await api.put("/v1/chats/7/settings", json={"lang": "en"})
        assert both.json() == {"chat_id": 7, "lang": "en", "profanity": "max"}  # kept
        assert (await api.put("/v1/chats/7/settings", json={})).status_code == 422
        assert (
            await api.put("/v1/chats/7/settings", json={"profanity": "mild"})
        ).status_code == 422
    async for api in api_factory():  # after a restart
        await api.put("/v1/chats/7/settings", json={"profanity": "roast"})
        assert (await api.get("/v1/chats/7/settings")).json() == {
            "chat_id": 7,
            "lang": "en",
            "profanity": "roast",
        }
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(ChatSetting)) == 1
