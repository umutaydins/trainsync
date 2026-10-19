"""DEMO_MODE (P7.9, ADR 0028): every write route answers 403, generated from the OpenAPI spec.

The operation lists come from `app.openapi()`, so a write route added later is covered (and
this test checks it) without anyone remembering to add it here.
"""

import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from tests.conftest import make_settings
from trainsync.entrypoints.api.app import create_app
from trainsync.entrypoints.api.middleware import DEMO_DETAIL, DEMO_HEADER, is_demo_blocked

KEY = {"X-API-Key": "test-api-key"}
SAMPLE_PATH_VALUES = {
    "integer": "1",
    "date": "2026-10-18",
    "uuid": "6f1c2b9e-3d4a-4f5e-8a7b-9c0d1e2f3a4b",
    "string": "x",
}
SPEC = create_app(make_settings()).openapi()


def _sample(path: str, op: dict[str, Any]) -> str:
    """The path with every `{param}` filled in by a value of its declared type."""
    values = {}
    for param in op.get("parameters", []):
        if param["in"] == "path":
            schema = param.get("schema", {})
            kind = schema.get("format") or schema.get("type", "string")
            values[param["name"]] = SAMPLE_PATH_VALUES.get(kind, "x")
    return re.sub(r"\{(\w+)\}", lambda m: values[m.group(1)], path)


def _operations(*, blocked: bool) -> list[tuple[str, str]]:
    return [
        (method.upper(), _sample(path, op))
        for path, ops in SPEC["paths"].items()
        for method, op in ops.items()
        if is_demo_blocked(method, path) is blocked
    ]


WRITES = _operations(blocked=True)
READS = _operations(blocked=False)


def test_the_spec_has_writes_and_reads() -> None:
    methods = {method for method, _ in WRITES}
    assert {"POST", "PUT", "PATCH", "DELETE"} <= methods
    assert ("POST", "/webhooks/strava") in WRITES
    assert ("GET", "/auth/strava/callback") in WRITES
    # Signing in and out of the published demo account are the only writes let through.
    assert {op for op in READS if op[0] != "GET"} == {
        ("POST", "/v1/auth/login"),
        ("POST", "/v1/auth/logout"),
    }
    assert ("GET", "/v1/activities") in READS


async def _client(demo: bool) -> AsyncIterator[httpx.AsyncClient]:
    # No lifespan: whatever passes the guard fails later (no DB), which is never the demo 403.
    app = create_app(make_settings(demo_mode=demo))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def demo() -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(demo=True):
        yield client


@pytest.fixture
async def normal() -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(demo=False):
        yield client


@pytest.mark.parametrize(("method", "path"), WRITES, ids=[f"{m} {p}" for m, p in WRITES])
async def test_every_write_is_403_in_demo_mode(
    demo: httpx.AsyncClient, normal: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await demo.request(method, path, headers=KEY, json={})
    assert response.status_code == 403
    assert response.json() == {"detail": DEMO_DETAIL}
    assert response.headers[DEMO_HEADER] == "read-only"
    assert response.headers["x-request-id"]

    without = await normal.request(method, path, headers=KEY, json={})
    assert DEMO_HEADER not in without.headers
    # Some writes are 403 for their own reason (the bot's service routes need a service key).
    assert without.status_code != 403 or without.json() != {"detail": DEMO_DETAIL}


@pytest.mark.parametrize(("method", "path"), READS, ids=[f"{m} {p}" for m, p in READS])
async def test_reads_pass_the_guard(demo: httpx.AsyncClient, method: str, path: str) -> None:
    response = await demo.request(method, path, headers=KEY)
    assert DEMO_HEADER not in response.headers


async def test_health_and_unknown_writes(demo: httpx.AsyncClient) -> None:
    assert (await demo.get("/health/live")).status_code == 200
    # Not in the spec either: refused before routing.
    response = await demo.post("/v1/something-new")
    assert response.status_code == 403
    assert (await demo.options("/v1/activities")).status_code != 403


@pytest.mark.parametrize(
    ("method", "path", "blocked"),
    [
        ("GET", "/v1/activities", False),
        ("head", "/v1/activities", False),
        ("OPTIONS", "/v1/activities", False),
        ("POST", "/v1/training/programs/generate", True),
        ("GET", "/auth/strava/login", True),
        ("GET", "/auth/strava/callback", True),
        ("GET", "/webhooks/strava", False),
        ("POST", "/webhooks/strava", True),
        ("delete", "/v1/nutrition/log/x", True),
        ("POST", "/v1/auth/login", False),
        ("post", "/v1/auth/logout", False),
        ("POST", "/v1/auth/register", True),
        ("POST", "/v1/auth/reset", True),
        ("DELETE", "/v1/me", True),
    ],
)
def test_is_demo_blocked(method: str, path: str, blocked: bool) -> None:
    assert is_demo_blocked(method, path) is blocked
