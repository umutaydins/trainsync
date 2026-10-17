"""Fault-injection suite (`make test-fault`): one module per row of the failure-modes table in
docs/architecture.md. Uses the same testcontainers fixtures as the integration tests."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from fake_strava.app import create_app as create_fake_strava
from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from trainsync.core.settings import Settings
from trainsync.main import create_app

_HERE = Path(__file__).resolve().parent
SUBSCRIPTION = 999  # STRAVA_WEBHOOK_SUBSCRIPTION_ID in the test settings
API_URL = "http://api"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if _HERE in item.path.parents:
            item.add_marker(pytest.mark.fault)


@pytest.fixture(autouse=True)
def _clean_state(clean_state: None) -> None:
    """Every fault test starts from empty tables and an empty Redis."""


@pytest.fixture
async def api_app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(api_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url=API_URL) as client:
        yield client


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(
        seed_activities=400,
        rate_limit_15min=100_000,
        rate_limit_daily=1_000_000,
        webhook_subscription_id=SUBSCRIPTION,
    )


@pytest.fixture
def fake_strava_app(
    fake_strava_config: FakeStravaConfig, fake_clock: FakeClock, api_app: FastAPI
) -> FastAPI:
    """fake_strava whose webhooks go straight into the trainsync app."""
    return create_fake_strava(fake_strava_config, fake_clock, httpx.ASGITransport(app=api_app))
