import httpx

from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app


def _client(settings: Settings) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(settings))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_health_live_sets_request_id(settings: Settings) -> None:
    async with _client(settings) as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) == 32


async def test_provided_request_id_is_echoed(settings: Settings) -> None:
    async with _client(settings) as client:
        response = await client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


async def test_importing_main_needs_no_env() -> None:
    import importlib

    import trainsync.entrypoints.api.app

    importlib.reload(trainsync.entrypoints.api.app)
