from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import make_settings
from trainsync.api import deps
from trainsync.core.settings import Settings
from trainsync.core.state import sign_state, verify_state
from trainsync.main import create_app

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected use: {name}")

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected call")


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    app.state.clock = lambda: NOW
    for dep in (deps.get_sessionmaker, deps.get_strava_client, deps.get_job_queue):
        app.dependency_overrides[dep] = MustNotBeUsed
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_login_redirects_with_required_params() -> None:
    settings = make_settings(strava_oauth_public_base_url="http://localhost:8001/oauth")
    async with _client(_app(settings)) as client:
        response = await client.get("/auth/strava/login")
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "http://localhost:8001/oauth/authorize"
    )
    query = {k: v[0] for k, v in parse_qs(location.query).items()}
    assert query["client_id"] == "1234"
    assert query["redirect_uri"] == settings.strava_redirect_uri
    assert query["response_type"] == "code"
    assert query["approval_prompt"] == "auto"
    assert query["scope"] == "read,activity:read_all"
    verify_state(query["state"], NOW, settings.state_signing_key)


def test_public_oauth_url_defaults_to_internal() -> None:
    settings = make_settings(strava_oauth_base_url="http://internal/oauth")
    assert settings.strava_oauth_public_base_url == "http://internal/oauth"


@pytest.mark.parametrize(
    ("params", "detail"),
    [
        ({"state": "garbage", "code": "c", "scope": "read,activity:read_all"}, "state"),
        ({"state": "EXPIRED", "code": "c", "scope": "read,activity:read_all"}, "state"),
        ({"state": "VALID", "code": "c", "scope": "read"}, "activity:read_all"),
        ({"state": "VALID", "error": "access_denied"}, "access_denied"),
        ({"state": "VALID", "scope": "read,activity:read_all"}, "missing code"),
    ],
    ids=["bad-state", "expired-state", "missing-scope", "access-denied", "no-code"],
)
async def test_callback_rejections_write_nothing(
    settings: Settings, params: dict[str, str], detail: str
) -> None:
    if params["state"] == "VALID":
        params["state"] = sign_state(NOW - timedelta(minutes=1), settings.state_signing_key)
    elif params["state"] == "EXPIRED":
        params["state"] = sign_state(NOW - timedelta(minutes=11), settings.state_signing_key)
    async with _client(_app(settings)) as client:
        response = await client.get("/auth/strava/callback", params=params)
    assert response.status_code == 400
    assert detail in response.json()["detail"]
