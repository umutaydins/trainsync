from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import FAKE_STRAVA_BASE_URL
from trainsync.core import deps
from trainsync.core.crypto import TokenCipher
from trainsync.core.jobs import ArqJobQueue
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.strava.models import Athlete, OAuthToken

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
    app.dependency_overrides[deps.get_strava_client] = lambda: strava
    async with LifespanManager(app):
        yield app


async def _connect(
    app: FastAPI, fake: httpx.AsyncClient, login_params: dict[str, str] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as api:
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
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as api:
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
    app.dependency_overrides[deps.get_strava_client] = lambda: strava
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
