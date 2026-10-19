from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.conftest import FAKE_STRAVA_BASE_URL
from tests.support.accounts import API_KEY, create_user, login, signed_in
from trainsync.core.crypto import TokenCipher
from trainsync.core.jobs import ArqJobQueue
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.strava import dependencies as strava_deps
from trainsync.modules.strava.models import Athlete, OAuthToken
from trainsync.modules.sync.deauthorization import deauthorize
from trainsync.modules.sync.disconnect import revoke_at_strava

PUBLIC_OAUTH = "http://localhost:8001/oauth"


@pytest.fixture
async def app(
    integration_settings: Settings, fake_strava_client: httpx.AsyncClient
) -> AsyncIterator[FastAPI]:
    settings = integration_settings.model_copy(
        update={
            "strava_oauth_base_url": f"{FAKE_STRAVA_BASE_URL}/oauth",
            "strava_oauth_public_base_url": PUBLIC_OAUTH,
        }
    )
    app = create_app(settings)
    strava = StravaClient(fake_strava_client, settings)
    app.dependency_overrides[strava_deps.get_strava_client] = lambda: strava
    async with LifespanManager(app):
        yield app


async def _connect(
    app: FastAPI,
    fake: httpx.AsyncClient,
    login_params: dict[str, str] | None = None,
    *,
    auth: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api", headers=auth or {"X-API-Key": API_KEY}
    ) as api:
        login = await api.get("/auth/strava/login", params=login_params)
        authorize_url = urlsplit(login.headers["location"])
        assert f"{authorize_url.scheme}://{authorize_url.netloc}" == "http://localhost:8001"
        # The browser would follow this to fake_strava; we replay it on the in-process fake.
        authorize = await fake.get(f"/oauth/authorize?{authorize_url.query}")
        callback = urlsplit(authorize.headers["location"])
        params = {k: v[0] for k, v in parse_qs(callback.query).items()}
        return await api.get("/auth/strava/callback", params=params)


async def _queued(app: FastAPI) -> list[str]:
    queue: ArqJobQueue = app.state.job_queue
    return [job.job_id or "" for job in await queue.pool.queued_jobs()]


async def test_connect_stores_athlete_encrypted_tokens_and_enqueues_backfill(
    app: FastAPI,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
) -> None:
    response = await _connect(app, fake_strava_client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strava_athlete_id"] == 1001
    assert body["backfill"] == "queued"

    async with sessionmaker() as session:
        athletes = (await session.scalars(select(Athlete))).all()
        tokens = (await session.scalars(select(OAuthToken))).all()
    assert [(a.id, a.strava_athlete_id, a.active) for a in athletes] == [
        (body["athlete_id"], 1001, True)
    ]
    assert len(tokens) == 1
    cipher = TokenCipher.from_settings(integration_settings)
    access = cipher.decrypt(tokens[0].access_token_enc)
    assert access.encode() not in tokens[0].access_token_enc
    assert tokens[0].scope == "read,activity:read_all"
    assert await _queued(app) == [f"backfill:{body['athlete_id']}"]


async def test_token_exchange_uses_internal_url(
    app: FastAPI, fake_strava_client: httpx.AsyncClient
) -> None:
    await _connect(app, fake_strava_client)
    stats = (await fake_strava_client.get("/_control/stats")).json()["requests"]
    assert stats["POST /oauth/token"] == {"200": 1}


async def test_double_callback_keeps_one_athlete_and_one_job(
    app: FastAPI,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    first = await _connect(app, fake_strava_client)
    second = await _connect(app, fake_strava_client)
    assert first.status_code == second.status_code == 200
    assert first.json()["athlete_id"] == second.json()["athlete_id"]
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Athlete)) == 1
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 1
    assert len(await _queued(app)) == 1


async def test_reconnect_reactivates_athlete_and_replaces_tokens(
    app: FastAPI,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _connect(app, fake_strava_client)
    async with sessionmaker.begin() as session:
        old = await session.scalar(select(OAuthToken.access_token_enc))
        await session.execute(update(Athlete).values(active=False))
    await _connect(app, fake_strava_client)
    async with sessionmaker() as session:
        assert await session.scalar(select(Athlete.active)) is True
        assert await session.scalar(select(OAuthToken.access_token_enc)) != old


async def test_rejected_code_writes_nothing(
    app: FastAPI,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api", headers={"X-API-Key": API_KEY}
    ) as api:
        login = await api.get("/auth/strava/login")
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        response = await api.get(
            "/auth/strava/callback",
            params={"state": state, "code": "bogus", "scope": "read,activity:read_all"},
        )
    assert response.status_code == 400
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Athlete)) == 0
    assert await _queued(app) == []


async def test_connect_with_return_to_lands_back_on_the_dashboard(
    integration_settings: Settings,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    settings = integration_settings.model_copy(
        update={
            "strava_oauth_base_url": f"{FAKE_STRAVA_BASE_URL}/oauth",
            "strava_oauth_public_base_url": PUBLIC_OAUTH,
            "oauth_return_to_allowlist": ["http://localhost:3000/sync"],
        }
    )
    app = create_app(settings)
    strava = StravaClient(fake_strava_client, settings)
    app.dependency_overrides[strava_deps.get_strava_client] = lambda: strava
    async with LifespanManager(app):
        response = await _connect(
            app, fake_strava_client, {"return_to": "http://localhost:3000/sync"}
        )
        queued = await _queued(app)
    assert len(queued) == 1
    assert queued[0].startswith("backfill:")
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/sync?connected=1"
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Athlete)) == 1


async def test_an_athlete_belongs_to_one_user_and_the_state_names_who_connects(
    app: FastAPI,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """P8.3, ADR 0037: the callback binds the athlete to the user in the signed state."""
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    alice_token = (await login(app, alice))["token"]
    bob_token = (await login(app, bob))["token"]
    connected = await _connect(
        app, fake_strava_client, auth={"Authorization": f"Bearer {alice_token}"}
    )
    assert connected.status_code == 200, connected.text
    async with sessionmaker() as session:
        assert await session.scalar(select(Athlete.user_id)) == alice.id
    taken = await _connect(app, fake_strava_client, auth={"Authorization": f"Bearer {bob_token}"})
    assert taken.status_code == 409
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Athlete)) == 1
        assert await session.scalar(select(OAuthToken.user_id)) == alice.id

    async with signed_in(app, alice) as api:
        status = (await api.get("/v1/me/strava")).json()
        assert (status["connected"], status["strava_athlete_id"]) == (True, 1001)
        url = (await api.post("/v1/me/strava/authorize-url")).json()["url"]
        assert url.startswith(f"{PUBLIC_OAUTH}/authorize?")
        assert (await api.delete("/v1/me/strava")).status_code == 204
        assert (await api.get("/v1/me/strava")).json()["connected"] is False
        assert (await api.delete("/v1/me/strava")).status_code == 404
    assert "strava_disconnect:1" in await _queued(app)
    async with signed_in(app, bob) as api:
        assert (await api.get("/v1/me/strava")).json() == {
            "connected": False,
            "athlete_id": None,
            "strava_athlete_id": None,
            "connected_at": None,
        }


async def test_strava_disconnect_revokes_at_strava_then_deletes_the_athlete_data(
    app: FastAPI,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
) -> None:
    await _connect(app, fake_strava_client)
    async with sessionmaker() as session:
        athlete_id = await session.scalar(select(Athlete.id))
        stored = await session.scalar(select(OAuthToken.access_token_enc))
    assert athlete_id is not None
    assert stored is not None
    access = TokenCipher.from_settings(integration_settings).decrypt(stored)

    class Tokens:
        async def access_token(self, athlete: int) -> str:
            return access

        async def force_refresh(self, athlete: int) -> str:
            return access

    strava = StravaClient(fake_strava_client, integration_settings, Tokens())
    assert await revoke_at_strava(strava, athlete_id) is True
    assert fake_strava.deauthorized == [fake_strava.default_athlete_id]
    assert await revoke_at_strava(strava, athlete_id) is False  # the token is dead now: logged
    async with sessionmaker.begin() as session:
        await deauthorize(session, athlete_id)
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 0
