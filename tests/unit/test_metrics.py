import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from tests.conftest import make_settings
from trainsync.api import deps
from trainsync.main import create_app
from trainsync.strava.breaker import CircuitBreaker
from trainsync.strava.errors import StravaUnavailable


class MustNotBeUsed:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected use: {name}")


def _app() -> FastAPI:
    app = create_app(make_settings())
    for dep in (deps.get_sessionmaker, deps.get_job_queue, deps.get_redis):
        app.dependency_overrides[dep] = MustNotBeUsed
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _http_count(route: str) -> float:
    value = REGISTRY.get_sample_value("http_request_duration_seconds_count", {"route": route})
    return value or 0.0


async def test_http_duration_is_labelled_by_route_template() -> None:
    app = _app()
    before = _http_count("/v1/activities")
    async with _client(app) as client:
        await client.get("/v1/activities?cursor=abc&limit=3", headers={"X-API-Key": "test-api-key"})
        await client.get("/v1/activities/../activities")
        await client.get("/no/such/path/123")
        metrics = (await client.get("/metrics")).text
    assert _http_count("/v1/activities") >= before + 1
    assert _http_count("unmatched") >= 1
    routes = {
        line.split('route="', 1)[1].split('"', 1)[0]
        for line in metrics.splitlines()
        if line.startswith("http_request_duration_seconds_count")
    }
    assert "/v1/activities" in routes
    assert not any("?" in r or "123" in r or ".." in r for r in routes), routes


async def test_metrics_endpoint_exposes_all_metric_families() -> None:
    async with _client(_app()) as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    for name in (
        "strava_requests_total",
        "strava_request_duration_seconds",
        "strava_retries_total",
        "strava_circuit_state",
        "strava_ratelimit_usage_ratio",
        "sync_jobs_total",
        "webhook_events_total",
        "http_request_duration_seconds",
    ):
        assert f"# TYPE {name.removesuffix('_total')}" in response.text, name


async def test_opening_the_breaker_sets_circuit_state_to_2() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    for _ in range(2):
        with pytest.raises(StravaUnavailable):
            async with breaker.guard():
                raise StravaUnavailable("503")
    assert REGISTRY.get_sample_value("strava_circuit_state") == 2
