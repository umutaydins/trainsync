"""P8.4, P8.5, ADR 0036: one-time link codes, the bot's chat lookups and per-user settings."""

from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.accounts import API_KEY, Account, client, create_user, signed_in
from trainsync.entrypoints.api.app import create_app

SERVICE_KEY = "bot-service-key"
CHAT = 7001


@pytest.fixture
async def app(pg_url: str, redis_url: str) -> AsyncIterator[FastAPI]:
    settings = make_settings(
        database_url=pg_url,
        redis_url=redis_url,
        api_keys=f"{API_KEY},{SERVICE_KEY}",
        service_api_keys=SERVICE_KEY,
        telegram_bot_username="trainsync_bot",
        bot_tone="neutral",
        emergency_number="112",
    )
    app = create_app(settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def bot(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with client(app, **{"X-API-Key": SERVICE_KEY}) as api:
        yield api


@pytest.fixture
async def alice(sessionmaker: async_sessionmaker[AsyncSession]) -> Account:
    return await create_user(sessionmaker, "alice@example.com", timezone="Europe/Berlin")


async def _code(app: FastAPI, account: Account) -> str:
    async with signed_in(app, account) as api:
        body = (await api.post("/v1/me/telegram/code")).json()
    assert body["command"] == f"/link {body['code']}"
    assert body["bot_url"] == f"https://t.me/trainsync_bot?start={body['code']}"
    code: str = body["code"]
    return code


async def test_link_once_lookup_and_unlink(
    app: FastAPI, bot: httpx.AsyncClient, alice: Account
) -> None:
    assert (await bot.get(f"/v1/telegram/chats/{CHAT}")).status_code == 404
    code = await _code(app, alice)
    linked = await bot.post(f"/v1/telegram/chats/{CHAT}/link", json={"code": code.lower()})
    assert linked.status_code == 200, linked.text
    owner = linked.json()
    assert (owner["user_id"], owner["role"], owner["settings"]["timezone"]) == (
        alice.id,
        "user",
        "Europe/Berlin",
    )
    again = await bot.post(f"/v1/telegram/chats/{CHAT}/link", json={"code": code})
    assert again.status_code == 400  # one use only
    assert (await bot.get(f"/v1/telegram/chats/{CHAT}")).json()["user_id"] == alice.id
    async with signed_in(app, alice) as api:
        assert (await api.get("/v1/me/telegram")).json()["linked"] is True
    assert (await bot.delete(f"/v1/telegram/chats/{CHAT}")).status_code == 204
    assert (await bot.get(f"/v1/telegram/chats/{CHAT}")).status_code == 404
    async with signed_in(app, alice) as api:
        assert (await api.get("/v1/me/telegram")).json() == {"linked": False, "linked_at": None}
        assert (await api.delete("/v1/me/telegram")).status_code == 404


async def test_a_new_chat_replaces_the_old_one_and_unknown_codes_fail(
    app: FastAPI, bot: httpx.AsyncClient, alice: Account
) -> None:
    await bot.post(f"/v1/telegram/chats/{CHAT}/link", json={"code": await _code(app, alice)})
    await bot.post("/v1/telegram/chats/7002/link", json={"code": await _code(app, alice)})
    assert (await bot.get(f"/v1/telegram/chats/{CHAT}")).status_code == 404
    assert (await bot.get("/v1/telegram/chats/7002")).json()["user_id"] == alice.id
    assert (
        await bot.post(f"/v1/telegram/chats/{CHAT}/link", json={"code": "NOPE2345"})
    ).status_code == 400
    async with signed_in(app, alice) as api:
        assert (await api.delete("/v1/me/telegram")).status_code == 204
    assert (await bot.get("/v1/telegram/chats/7002")).status_code == 404


async def test_only_the_service_key_reaches_the_chat_routes(app: FastAPI, alice: Account) -> None:
    async with client(app, **{"X-API-Key": API_KEY}) as owner_tooling:
        assert (await owner_tooling.get(f"/v1/telegram/chats/{CHAT}")).status_code == 403
    async with client(app) as anonymous:
        assert (await anonymous.get(f"/v1/telegram/chats/{CHAT}")).status_code == 401
    async with signed_in(app, alice) as api:
        assert (await api.get(f"/v1/telegram/chats/{CHAT}")).status_code == 401


async def test_settings_defaults_overrides_reset_and_emergency_number(
    app: FastAPI, bot: httpx.AsyncClient, alice: Account
) -> None:
    async with signed_in(app, alice) as api:
        defaults = (await api.get("/v1/me/settings")).json()
        assert (defaults["tone"], defaults["lang"], defaults["custom"]) == ("neutral", "en", [])
        assert (defaults["emergency_number"], defaults["timezone"]) == ("112", "Europe/Berlin")
        changed = await api.patch(
            "/v1/me/settings", json={"lang": "tr", "country": "US", "quiet_hours": "22:00-06:00"}
        )
        assert changed.status_code == 200, changed.text
        body = changed.json()
        assert (body["lang"], body["emergency_number"], body["quiet_hours"]) == (
            "tr",
            "911",
            "22:00-06:00",
        )
        assert sorted(body["custom"]) == ["country", "lang", "quiet_hours"]
        reset = (await api.patch("/v1/me/settings", json={"country": None})).json()
        assert (reset["emergency_number"], reset["lang"]) == ("112", "tr")
        assert (await api.patch("/v1/me/settings", json={"quiet_hours": "late"})).status_code == 422
        assert (await api.patch("/v1/me/settings", json={"country": "de"})).status_code == 422
    # The bot acts as the linked user: /lang stores into their settings.
    await bot.post(f"/v1/telegram/chats/{CHAT}/link", json={"code": await _code(app, alice)})
    as_alice = {"X-Acting-User": str(alice.id)}
    stored = await bot.patch("/v1/me/settings", json={"profanity": "max"}, headers=as_alice)
    assert stored.json()["profanity"] == "max"
    assert (await bot.get(f"/v1/telegram/chats/{CHAT}")).json()["settings"]["profanity"] == "max"
