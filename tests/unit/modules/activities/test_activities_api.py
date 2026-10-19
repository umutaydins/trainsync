import base64
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from tests.conftest import make_settings
from trainsync.core import deps
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.activities.reads import Keyset
from trainsync.modules.activities.router import decode_cursor, encode_cursor
from trainsync.modules.auth.dependencies import current_principal
from trainsync.modules.auth.models import UserRole
from trainsync.modules.auth.service import Principal


class MustNotBeUsed:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected use: {name}")


def _app(*, signed_in: bool = False) -> FastAPI:
    app = create_app(make_settings(api_keys="key-one, key-two"))
    app.dependency_overrides[deps.get_sessionmaker] = MustNotBeUsed
    if signed_in:  # whoever the key names; these tests never reach the database
        app.dependency_overrides[current_principal] = lambda: Principal(1, UserRole.OWNER, "UTC")
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": ""}, {"X-API-Key": "wrong"}, {"X-API-Key": "key-one "}],
    ids=["missing", "empty", "wrong", "trailing-space"],
)
async def test_missing_or_wrong_key_is_401(headers: dict[str, str]) -> None:
    async with _client(_app()) as client:
        response = await client.get("/v1/activities", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64!!",
        base64.urlsafe_b64encode(b"not json").decode(),
        base64.urlsafe_b64encode(b'{"id": 1}').decode(),
        base64.urlsafe_b64encode(
            b'{"start_date": "2026-10-01T00:00:00+00:00", "id": "1"}'
        ).decode(),
        base64.urlsafe_b64encode(b'{"start_date": "2026-10-01T00:00:00", "id": 1}').decode(),
    ],
    ids=["junk", "not-json", "missing-field", "string-id", "naive-date"],
)
async def test_invalid_cursor_is_400(cursor: str) -> None:
    async with _client(_app(signed_in=True)) as client:
        response = await client.get(
            "/v1/activities", params={"cursor": cursor}, headers={"X-API-Key": "key-two"}
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid cursor"}


@pytest.mark.parametrize("limit", [0, 201])
async def test_limit_out_of_range_is_422(limit: int) -> None:
    async with _client(_app(signed_in=True)) as client:
        response = await client.get(
            "/v1/activities", params={"limit": limit}, headers={"X-API-Key": "key-one"}
        )
    assert response.status_code == 422


def test_cursor_round_trip() -> None:
    keyset = Keyset(datetime(2026, 10, 1, 6, 30, tzinfo=UTC), 42)
    assert decode_cursor(encode_cursor(keyset)) == keyset


def test_decode_error_is_http_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_cursor("%%%")
    assert exc_info.value.status_code == 400
