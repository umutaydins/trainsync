"""P6.11: training writes queue the coach's jobs (once per object), and a broken queue never fails
the write (ADR 0030)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import OWNER_ID
from trainsync.core import deps
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.training.repository import ExerciseRepository

pytestmark = pytest.mark.integration

KEY = {"X-API-Key": "test-api-key"}
NOW = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api", headers=KEY) as client:
        yield client


async def queued(app: FastAPI, job_id: str) -> bool:
    pool: ArqRedis = app.state.job_queue.pool
    return await Job(job_id, pool).status() == JobStatus.queued


async def bench_id(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        exercise = await ExerciseRepository(session, OWNER_ID).by_slug("bench-press")
        assert exercise is not None
        return exercise.id


async def test_start_set_and_finish_queue_their_coach_jobs_once(
    app: FastAPI, api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    start = f"/v1/training/workouts/{uuid.uuid4()}"
    workout = (await api.put(start, json={})).json()
    assert await queued(app, f"coach_workout_started:{workout['id']}")
    pool: ArqRedis = app.state.job_queue.pool
    before = await pool.zcard("arq:queue")
    assert (await api.put(start, json={})).status_code == 200  # a retry queues nothing new
    assert await pool.zcard("arq:queue") == before

    body = {
        "exercise_id": await bench_id(sessionmaker),
        "set_index": 1,
        "reps": 5,
        "weight_kg": "80",
        "completed_at": NOW.isoformat(),
    }
    set_url = f"/v1/training/workouts/{workout['id']}/sets/{uuid.uuid4()}"
    assert (await api.put(set_url, json=body)).status_code == 201
    assert (await api.put(set_url, json=body)).status_code == 200
    assert await pool.zcard("arq:queue") == before + 1  # only the new set

    finish = f"/v1/training/workouts/{workout['id']}/finish"
    assert (await api.post(finish, json={})).status_code == 200
    assert await queued(app, f"coach_workout_finished:{workout['id']}")


class BrokenEvents:
    async def coach_event(self, job: str, object_id: int) -> None:
        raise ConnectionError("redis is down")


async def test_a_broken_queue_never_fails_the_write(app: FastAPI, api: httpx.AsyncClient) -> None:
    app.dependency_overrides[deps.get_coach_events] = BrokenEvents
    response = await api.put(f"/v1/training/workouts/{uuid.uuid4()}", json={})
    assert response.status_code == 201
