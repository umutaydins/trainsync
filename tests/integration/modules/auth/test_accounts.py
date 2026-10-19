"""P8.1, ADR 0034: registration modes, invites, sessions, limits, resets and the owner API."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.accounts import (
    API_KEY,
    OWNER_EMAIL,
    OWNER_ID,
    PASSWORD,
    Account,
    client,
    create_user,
    login,
    signed_in,
)
from trainsync.core.security import token_hash
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.auth.models import AuthSession, User

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> Clock:
    return Clock()


async def _app(settings: Settings, clock: Clock) -> FastAPI:
    app = create_app(settings)
    app.state.clock = clock
    return app


@pytest.fixture
def mode() -> str:
    return "invite"


@pytest.fixture
async def app(pg_url: str, redis_url: str, clock: Clock, mode: str) -> AsyncIterator[FastAPI]:
    settings = make_settings(
        database_url=pg_url,
        redis_url=redis_url,
        registration_mode=mode,
        dashboard_public_url="https://dash.example",
        service_api_keys="bot-service-key",
        api_keys="test-api-key,bot-service-key",
    )
    app = await _app(settings, clock)
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def owner_api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with client(app, **{"X-API-Key": API_KEY}) as api:
        yield api


async def _invite(owner_api: httpx.AsyncClient) -> str:
    response = await owner_api.post("/v1/admin/invites", json={"note": "for a friend"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["url"] == f"https://dash.example/register?invite={body['code']}"
    code: str = body["code"]
    return code


async def _register(app: FastAPI, email: str, **extra: object) -> httpx.Response:
    async with client(app) as anonymous:
        return await anonymous.post(
            "/v1/auth/register", json={"email": email, "password": PASSWORD, **extra}
        )


# ---------------------------------------------------------------- registration


async def test_invite_mode_needs_an_unused_unexpired_invite(
    app: FastAPI, owner_api: httpx.AsyncClient, clock: Clock
) -> None:
    async with client(app) as anonymous:
        assert (await anonymous.get("/v1/auth/registration")).json() == {"mode": "invite"}
    assert (await _register(app, "a@example.com")).status_code == 400
    assert (await _register(app, "a@example.com", invite_code="nope")).status_code == 400
    code = await _invite(owner_api)
    created = await _register(app, " A@Example.com ", invite_code=code, timezone="Europe/Berlin")
    assert created.status_code == 201, created.text
    assert created.json() | {"created_at": None} == {
        "id": created.json()["id"],
        "email": "a@example.com",
        "display_name": "a",
        "role": "user",
        "timezone": "Europe/Berlin",
        "created_at": None,
    }
    assert (await _register(app, "b@example.com", invite_code=code)).status_code == 400  # used
    late = await _invite(owner_api)
    clock.advance(days=8)
    assert (await _register(app, "c@example.com", invite_code=late)).status_code == 400
    invites = (await owner_api.get("/v1/admin/invites")).json()["items"]
    assert [i["status"] for i in invites] == ["expired", "used"]


async def test_a_revoked_invite_cannot_be_used(app: FastAPI, owner_api: httpx.AsyncClient) -> None:
    code = await _invite(owner_api)
    invite_id = (await owner_api.get("/v1/admin/invites")).json()["items"][0]["id"]
    assert (await owner_api.delete(f"/v1/admin/invites/{invite_id}")).status_code == 204
    assert (await owner_api.delete(f"/v1/admin/invites/{invite_id}")).status_code == 404
    assert (await _register(app, "a@example.com", invite_code=code)).status_code == 400


@pytest.mark.parametrize("mode", ["open"])
async def test_open_mode_needs_no_invite_and_emails_are_unique(app: FastAPI) -> None:
    assert (await _register(app, "a@example.com")).status_code == 201
    assert (await _register(app, "A@example.com")).status_code == 409
    weak = await _register(app, "b@example.com", password="short")
    assert weak.status_code == 422
    assert (await _register(app, "c@example.com", timezone="Mars/Base")).status_code == 400


@pytest.mark.parametrize("mode", ["closed"])
async def test_closed_mode_refuses_everyone(app: FastAPI, owner_api: httpx.AsyncClient) -> None:
    code = await _invite(owner_api)
    assert (await _register(app, "a@example.com", invite_code=code)).status_code == 403


@pytest.mark.parametrize("mode", ["open"])
async def test_registrations_per_address_are_limited(app: FastAPI) -> None:
    statuses = [(await _register(app, f"u{n}@example.com")).status_code for n in range(6)]
    assert statuses == [201] * 5 + [429]


# ---------------------------------------------------------------- sessions


async def test_login_me_logout_and_the_stored_hash(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    body = await login(app, account)
    assert body["user"]["email"] == "a@example.com"
    async with sessionmaker() as session:
        stored = await session.scalar(select(AuthSession.token_hash))
    assert stored == token_hash(body["token"])
    async with client(app, Authorization=f"Bearer {body['token']}") as api:
        assert (await api.get("/v1/me")).json()["id"] == account.id
        assert (await api.post("/v1/auth/logout")).status_code == 204
        assert (await api.get("/v1/me")).status_code == 401
    async with client(app, Authorization="Bearer not-a-token") as api:
        assert (await api.get("/v1/me")).status_code == 401


async def test_wrong_password_and_unknown_email_get_the_same_answer(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await create_user(sessionmaker, "a@example.com")
    async with client(app) as anonymous:
        wrong = await anonymous.post(
            "/v1/auth/login", json={"email": "a@example.com", "password": "wrong password!"}
        )
        unknown = await anonymous.post(
            "/v1/auth/login", json={"email": "x@example.com", "password": "wrong password!"}
        )
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json())
    assert wrong.status_code == 401


async def test_expiry_slides_on_use_and_stops_at_the_cap(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    token = (await login(app, account))["token"]
    async with client(app, Authorization=f"Bearer {token}") as api:
        for _ in range(3):  # 3 x 29 days: alive only because each use slides the expiry
            clock.advance(days=29)
            assert (await api.get("/v1/me")).status_code == 200
        clock.advance(days=4)  # 91 days after sign-in: past SESSION_MAX_AGE_DAYS
        assert (await api.get("/v1/me")).status_code == 401
    idle = (await login(app, account))["token"]
    clock.advance(days=31)
    async with client(app, Authorization=f"Bearer {idle}") as api:
        assert (await api.get("/v1/me")).status_code == 401


async def test_sessions_list_and_revoke_only_my_own(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    alice = await create_user(sessionmaker, "a@example.com")
    bob = await create_user(sessionmaker, "b@example.com")
    bob_token = (await login(app, bob))["token"]
    await login(app, alice)
    async with signed_in(app, alice) as api:
        mine = (await api.get("/v1/me/sessions")).json()["items"]
        assert len(mine) == 2
        assert sum(s["current"] for s in mine) == 1
        async with sessionmaker() as session:
            bob_session = await session.scalar(
                select(AuthSession.id).where(AuthSession.token_hash == token_hash(bob_token))
            )
        assert (await api.delete(f"/v1/me/sessions/{bob_session}")).status_code == 404
        other = next(s["id"] for s in mine if not s["current"])
        assert (await api.delete(f"/v1/me/sessions/{other}")).status_code == 204
        assert len((await api.get("/v1/me/sessions")).json()["items"]) == 1
    async with client(app, Authorization=f"Bearer {bob_token}") as api:
        assert (await api.get("/v1/me")).status_code == 200


async def test_lockout_after_repeated_failures_even_with_the_right_password(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    async with client(app) as anonymous:
        bad = {"email": account.email, "password": "wrong password!"}
        statuses = [
            (await anonymous.post("/v1/auth/login", json=bad)).status_code for _ in range(5)
        ]
        assert statuses == [401] * 5
        good = {"email": account.email, "password": PASSWORD}
        locked = await anonymous.post("/v1/auth/login", json=good)
        assert locked.status_code == 429
        assert 0 < int(locked.headers["Retry-After"]) <= 15 * 60
        clock.advance(minutes=15)
        assert (await anonymous.post("/v1/auth/login", json=good)).status_code == 200


async def test_password_change_keeps_this_session_and_ends_the_others(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    other = (await login(app, account))["token"]
    async with signed_in(app, account) as api:
        wrong = {"current_password": "not it at all", "new_password": "a new long password"}
        assert (await api.post("/v1/me/password", json=wrong)).status_code == 401
        change = {"current_password": PASSWORD, "new_password": "a new long password"}
        assert (await api.post("/v1/me/password", json=change)).status_code == 204
        assert (await api.get("/v1/me")).status_code == 200
        renamed = await api.patch(
            "/v1/me", json={"display_name": "Alice", "timezone": "Asia/Tokyo"}
        )
        assert renamed.json()["display_name"] == "Alice"
        blank = await api.patch("/v1/me", json={"display_name": "   "})
        assert blank.status_code == 422
        assert (await api.get("/v1/me")).json()["display_name"] == "Alice"
    async with client(app, Authorization=f"Bearer {other}") as api:
        assert (await api.get("/v1/me")).status_code == 401
    await login(app, Account(account.id, account.email, "a new long password"))


async def test_reset_link_is_single_use_expires_and_ends_every_session(
    app: FastAPI,
    owner_api: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    clock: Clock,
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    old = (await login(app, account))["token"]
    link = (await owner_api.post(f"/v1/admin/users/{account.id}/reset-link")).json()
    token = link["url"].split("token=", 1)[1]
    assert link["url"].startswith("https://dash.example/reset-password?token=")
    async with client(app) as anonymous:
        body = {"token": token, "password": "brand new password"}
        assert (await anonymous.post("/v1/auth/reset", json=body)).status_code == 204
        assert (await anonymous.post("/v1/auth/reset", json=body)).status_code == 400
        late = (await owner_api.post(f"/v1/admin/users/{account.id}/reset-link")).json()
        clock.advance(minutes=61)
        expired = {"token": late["url"].split("token=", 1)[1], "password": "another password"}
        assert (await anonymous.post("/v1/auth/reset", json=expired)).status_code == 400
    async with client(app, Authorization=f"Bearer {old}") as api:
        assert (await api.get("/v1/me")).status_code == 401
    await login(app, Account(account.id, account.email, "brand new password"))
    assert (await owner_api.post("/v1/admin/users/999/reset-link")).status_code == 404


# ---------------------------------------------------------------- owner API and API keys


async def test_admin_is_owner_only_and_lists_accounts_without_data(
    app: FastAPI, owner_api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    async with signed_in(app, account) as api:
        assert (await api.get("/v1/admin/users")).status_code == 403
        assert (await api.post("/v1/admin/invites", json={})).status_code == 403
    users = (await owner_api.get("/v1/admin/users")).json()["items"]
    assert [(u["email"], u["role"]) for u in users] == [
        (OWNER_EMAIL, "owner"),
        (account.email, "user"),
    ]
    assert set(users[0]) == {"id", "email", "display_name", "role", "created_at"}


async def test_api_keys_act_as_the_owner_and_only_service_keys_act_as_others(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    account = await create_user(sessionmaker, "a@example.com")
    async with client(app, **{"X-API-Key": API_KEY}) as api:
        assert (await api.get("/v1/me")).json()["id"] == OWNER_ID
        acting = await api.get("/v1/me", headers={"X-Acting-User": str(account.id)})
        assert acting.status_code == 403
    async with client(app, **{"X-API-Key": "bot-service-key"}) as bot:
        acting = await bot.get("/v1/me", headers={"X-Acting-User": str(account.id)})
        assert acting.json()["id"] == account.id
        assert (await bot.get("/v1/me", headers={"X-Acting-User": "999"})).status_code == 401
    async with client(app, **{"X-API-Key": "wrong"}) as api:
        assert (await api.get("/v1/me")).status_code == 401


async def test_without_an_owner_api_keys_get_503(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker.begin() as session:
        owner = await session.get(User, OWNER_ID)
        assert owner is not None
        await session.delete(owner)
    async with client(app, **{"X-API-Key": API_KEY}) as api:
        assert (await api.get("/v1/me")).status_code == 503
