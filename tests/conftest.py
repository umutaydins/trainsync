from collections.abc import AsyncIterator, Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI

from fake_strava.app import create_app as create_fake_strava
from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from trainsync.core.settings import Settings, get_settings

TEST_FERNET_KEY = Fernet.generate_key().decode()

TEST_ENV = {
    "ENV": "test",
    "STRAVA_CLIENT_ID": "1234",
    "STRAVA_CLIENT_SECRET": "client-secret-value",
    "STRAVA_WEBHOOK_VERIFY_TOKEN": "verify-token-value",
    "STRAVA_WEBHOOK_SUBSCRIPTION_ID": "999",
    "TOKEN_ENCRYPTION_KEY": TEST_FERNET_KEY,
    "STATE_SIGNING_KEY": "state-signing-key-value",
    "API_KEYS": "test-api-key",
    "WORKER_METRICS_PORT": "0",
}


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {k.lower(): v for k, v in TEST_ENV.items()}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------- fake_strava (in-process)

FAKE_STRAVA_BASE_URL = "http://fake-strava"


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig()


@pytest.fixture
def fake_strava_app(fake_strava_config: FakeStravaConfig, fake_clock: FakeClock) -> FastAPI:
    return create_fake_strava(fake_strava_config, fake_clock)


@pytest.fixture
def fake_strava(fake_strava_app: FastAPI) -> FakeStravaState:
    """Direct handle on the fake's in-memory state."""
    state: FakeStravaState = fake_strava_app.state.fake
    return state


@pytest.fixture
async def fake_strava_client(fake_strava_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=fake_strava_app)
    async with httpx.AsyncClient(transport=transport, base_url=FAKE_STRAVA_BASE_URL) as client:
        yield client


async def fake_strava_login(
    client: httpx.AsyncClient, scope: str = "read,activity:read_all"
) -> dict[str, Any]:
    """Run authorize → token against the fake; returns the token response JSON."""
    authorize = await client.get(
        "/oauth/authorize",
        params={
            "client_id": "1234",
            "redirect_uri": "http://localhost/cb",
            "response_type": "code",
            "scope": scope,
            "state": "s",
        },
    )
    code = parse_qs(urlsplit(authorize.headers["location"]).query)["code"][0]
    response = await client.post(
        "/oauth/token",
        data={
            "client_id": "1234",
            "client_secret": "x",
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    token: dict[str, Any] = response.json()
    return token


@pytest.fixture
async def fake_strava_token(fake_strava_client: httpx.AsyncClient) -> dict[str, Any]:
    return await fake_strava_login(fake_strava_client)
