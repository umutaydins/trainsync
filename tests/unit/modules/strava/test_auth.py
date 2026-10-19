import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import make_settings
from trainsync.core import deps
from trainsync.core.settings import Settings
from trainsync.core.state import sign_state, verify_state
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.strava import dependencies as strava_deps

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected use: {name}")

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected call")


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    app.state.clock = lambda: NOW
    for dep in (deps.get_sessionmaker, strava_deps.get_strava_client, deps.get_job_queue):
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


# ---------------------------------------------------------------- return_to (P5.4)

RETURN_TO = "http://localhost:3000/sync"


def _return_to_settings() -> Settings:
    return make_settings(oauth_return_to_allowlist=f"{RETURN_TO},https://dash.example/sync")


async def _login_state(settings: Settings, return_to: str) -> str:
    async with _client(_app(settings)) as client:
        response = await client.get("/auth/strava/login", params={"return_to": return_to})
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def test_allowlist_is_read_from_a_comma_separated_env_value() -> None:
    assert _return_to_settings().oauth_return_to_allowlist == [
        RETURN_TO,
        "https://dash.example/sync",
    ]
    assert make_settings().oauth_return_to_allowlist == []


async def test_login_signs_an_allowlisted_return_to_into_the_state() -> None:
    settings = _return_to_settings()
    state = await _login_state(settings, RETURN_TO)
    assert verify_state(state, NOW, settings.state_signing_key) == RETURN_TO


@pytest.mark.parametrize(
    "return_to",
    [
        "https://evil.example/",
        "//evil.example/sync",
        "http://localhost:3000/sync.evil.example",
        "http://localhost:3000/sync/../../evil",
        "http://localhost:3000/sync?next=https://evil.example",
        "http://localhost:3000/sync@evil.example",
        "http://localhost:3000.evil.example/sync",
        "http://LOCALHOST:3000/sync",
        "http://localhost:3000/",
        "javascript:alert(1)",
        " http://localhost:3000/sync",
    ],
)
async def test_off_allowlist_return_to_is_ignored(return_to: str) -> None:
    settings = _return_to_settings()
    state = await _login_state(settings, return_to)
    assert verify_state(state, NOW, settings.state_signing_key) == ""
    assert len(state.split(".")) == 3


async def test_return_to_is_ignored_without_an_allowlist(settings: Settings) -> None:
    state = await _login_state(settings, RETURN_TO)
    assert verify_state(state, NOW, settings.state_signing_key) == ""


async def test_callback_redirects_errors_back_to_an_allowlisted_return_to() -> None:
    settings = _return_to_settings()
    state = sign_state(NOW, settings.state_signing_key, data=RETURN_TO)
    async with _client(_app(settings)) as client:
        response = await client.get(
            "/auth/strava/callback", params={"state": state, "error": "access_denied"}
        )
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == RETURN_TO
    assert parse_qs(location.query) == {
        "connect_error": ["strava authorization failed: access_denied"]
    }


async def test_callback_never_redirects_to_a_url_no_longer_allowlisted() -> None:
    """A state signed while a URL was allowlisted is re-checked against the current list."""
    settings = _return_to_settings()
    state = sign_state(NOW, settings.state_signing_key, data="https://evil.example/")
    async with _client(_app(settings)) as client:
        response = await client.get(
            "/auth/strava/callback", params={"state": state, "error": "access_denied"}
        )
    assert response.status_code == 400
    assert "location" not in response.headers


async def test_callback_with_a_tampered_return_to_is_rejected() -> None:
    settings = _return_to_settings()
    nonce, issued_at, _data, signature = sign_state(
        NOW, settings.state_signing_key, data=RETURN_TO
    ).split(".")
    evil = base64.urlsafe_b64encode(b"https://evil.example/").rstrip(b"=").decode()
    async with _client(_app(settings)) as client:
        response = await client.get(
            "/auth/strava/callback",
            params={"state": f"{nonce}.{issued_at}.{evil}.{signature}", "error": "x"},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid or expired state"
    assert "location" not in response.headers
