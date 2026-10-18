"""The demo reset (P7.9) against real Postgres: wipe + seed, idempotent, served read-only."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from arq import create_pool
from arq.worker import Worker
from asgi_lifespan import LifespanManager
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_ENV
from trainsync.core.settings import Settings, get_settings
from trainsync.db.models import Activity, Exercise, FoodLog, Workout
from trainsync.demo.__main__ import main as demo_cli
from trainsync.demo.store import DemoModeRequiredError, reset
from trainsync.demo.worker import DemoWorkerSettings
from trainsync.main import create_app
from trainsync.sync.queue import redis_settings

NOW = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)
KEY = {"X-API-Key": "test-api-key"}


@pytest.fixture
def demo_settings(integration_settings: Settings) -> Settings:
    return integration_settings.model_copy(update={"demo_mode": True})


async def _count(sessionmaker: async_sessionmaker[AsyncSession], model: type[object]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_reset_refuses_outside_demo_mode(
    integration_settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(DemoModeRequiredError):
        await reset(integration_settings, sessionmaker, lambda: NOW)


async def test_reset_wipes_and_seeds_the_same_data_twice(
    demo_settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker.begin() as session:
        session.add(
            Exercise(
                slug="custom-x",
                name="Custom",
                primary_muscle="core",
                equipment="bodyweight",
                is_custom=True,
            )
        )
    library = await _count(sessionmaker, Exercise) - 1

    first = await reset(demo_settings, sessionmaker, lambda: NOW)
    second = await reset(demo_settings, sessionmaker, lambda: NOW)

    assert first == second
    assert await _count(sessionmaker, Activity) == first.activities
    assert await _count(sessionmaker, Workout) == first.workouts
    assert await _count(sessionmaker, FoodLog) == first.food_logs
    assert await _count(sessionmaker, Exercise) == library


@pytest.fixture
async def demo_api(
    demo_settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    await reset(demo_settings, sessionmaker, lambda: NOW)
    app = create_app(demo_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            yield client


async def test_the_demo_api_serves_the_seed_and_refuses_writes(
    demo_api: httpx.AsyncClient,
) -> None:
    activities = (await demo_api.get("/v1/activities", headers=KEY)).json()
    assert len(activities["items"]) > 0
    workouts = (await demo_api.get("/v1/training/workouts", headers=KEY)).json()
    assert len(workouts["items"]) > 0
    active = await demo_api.get("/v1/training/programs/active", headers=KEY)
    assert active.json()["name"] == "Upper/Lower 4-day"
    checkins = await demo_api.get(
        "/v1/checkins", params={"from": "2026-10-01", "to": "2026-10-17"}, headers=KEY
    )
    assert checkins.status_code == 200
    assert len(checkins.json()["items"]) == 17
    status = (await demo_api.get("/v1/sync/status", headers=KEY)).json()
    assert status["athletes"][0]["incremental"]["status"] == "succeeded"
    nutrition = await demo_api.get("/v1/nutrition/summary/weekly", headers=KEY)
    assert nutrition.status_code == 200

    refused = await demo_api.put("/v1/nutrition/profile", headers=KEY, json={})
    assert refused.status_code == 403
    assert refused.json() == {"detail": "This is a read-only demo."}


async def test_the_demo_worker_runs_the_reset(
    demo_settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    worker = Worker(
        functions=DemoWorkerSettings.functions,
        on_startup=DemoWorkerSettings.on_startup,
        on_shutdown=DemoWorkerSettings.on_shutdown,
        redis_settings=redis_settings(demo_settings),
        ctx={"settings": demo_settings, "clock": lambda: NOW},
        burst=True,
        poll_delay=0.01,
        handle_signals=False,
    )
    pool = await create_pool(redis_settings(demo_settings))
    await pool.enqueue_job("demo_reset_job")
    await pool.aclose()
    try:
        await worker.async_run()
        assert worker.jobs_complete == 1
    finally:
        await worker.close()
    assert await _count(sessionmaker, Activity) > 0


def test_the_cli_resets_only_in_demo_mode(
    demo_settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {**TEST_ENV, "DATABASE_URL": demo_settings.database_url, "WORKER_METRICS_PORT": "0"}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DEMO_MODE", "false")
    assert demo_cli(["reset"]) == 2
    assert "DEMO_MODE is not true" in capsys.readouterr().err
    get_settings.cache_clear()
    monkeypatch.setenv("DEMO_MODE", "true")
    assert demo_cli(["reset"]) == 0
    assert "demo reset: ResetSummary(activities=" in capsys.readouterr().out
