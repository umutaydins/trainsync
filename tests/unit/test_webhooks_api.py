import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import make_settings
from trainsync.api import deps
from trainsync.api.webhooks import EXAMPLE_EVENT, StravaEvent
from trainsync.core.settings import Settings
from trainsync.main import create_app


class MustNotBeUsed:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected use: {name}")


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    for dep in (deps.get_sessionmaker, deps.get_strava_client, deps.get_job_queue):
        app.dependency_overrides[dep] = MustNotBeUsed
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _validation(token: str, mode: str = "subscribe") -> dict[str, str]:
    return {"hub.mode": mode, "hub.challenge": "abc123", "hub.verify_token": token}


async def test_validation_echoes_challenge(settings: Settings) -> None:
    async with _client(_app(settings)) as client:
        response = await client.get("/webhooks/strava", params=_validation("verify-token-value"))
    assert response.status_code == 200
    assert response.json() == {"hub.challenge": "abc123"}


@pytest.mark.parametrize(
    "params",
    [
        _validation("wrong-token"),
        _validation(""),
        _validation("verify-token-value", mode="unsubscribe"),
        {"hub.challenge": "abc123"},
    ],
    ids=["wrong-token", "empty-token", "wrong-mode", "missing"],
)
async def test_validation_rejects(params: dict[str, str], settings: Settings) -> None:
    async with _client(_app(settings)) as client:
        response = await client.get("/webhooks/strava", params=params)
    assert response.status_code == 403
    assert "abc123" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"object_type": "activity"}',
        b'{"object_type": "club", "object_id": 1, "aspect_type": "create", "owner_id": 1,'
        b' "subscription_id": 1, "event_time": 1}',
    ],
    ids=["junk", "array", "missing-fields", "unknown-object-type"],
)
async def test_malformed_event_is_400_and_touches_nothing(body: bytes, settings: Settings) -> None:
    async with _client(_app(settings)) as client:
        response = await client.post(
            "/webhooks/strava", content=body, headers={"content-type": "application/json"}
        )
    assert response.status_code == 400


async def test_event_for_other_subscription_is_acknowledged_and_ignored() -> None:
    settings = make_settings(strava_webhook_subscription_id="999")
    event = {**EXAMPLE_EVENT, "subscription_id": 1}
    async with _client(_app(settings)) as client:
        response = await client.post("/webhooks/strava", json=event)
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_dedup_key_covers_the_identifying_fields() -> None:
    event = StravaEvent.model_validate(EXAMPLE_EVENT)
    same = StravaEvent.model_validate({**EXAMPLE_EVENT, "updates": {"title": "other"}})
    assert event.dedup_key() == same.dedup_key()
    assert len(event.dedup_key()) == 64
    for field, value in [
        ("subscription_id", 1),
        ("object_type", "athlete"),
        ("object_id", 2),
        ("aspect_type", "create"),
        ("event_time", 3),
    ]:
        other = StravaEvent.model_validate({**EXAMPLE_EVENT, field: value})
        assert other.dedup_key() != event.dedup_key(), field
