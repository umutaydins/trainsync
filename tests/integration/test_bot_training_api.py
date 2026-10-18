"""P6.8 against the real API (Postgres via testcontainers, in-process ASGI): the program day
rotation behind `/today`, and a redelivered `/log` that must store its sets once."""

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.messages import NEUTRAL_EN as MSG
from tests.support.state import MemoryStateStore
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, message_update, ok, sent_messages
from trainsync.bot.common import RedisStateStore, client_id
from trainsync.bot.handlers import Commands, Dispatcher
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi, Update
from trainsync.bot.training import TrainingCommands
from trainsync.core.settings import Settings
from trainsync.db.models import Workout, WorkoutSet
from trainsync.db.repositories.training import ExerciseRepository
from trainsync.main import create_app

pytestmark = pytest.mark.integration

KEY = "test-api-key"
NOW = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
CHAT = 42


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api", headers={"X-API-Key": KEY}
    ) as client:
        yield client


async def ids(sessionmaker: async_sessionmaker[AsyncSession], *slugs: str) -> dict[str, int]:
    async with sessionmaker() as session:
        repo = ExerciseRepository(session)
        return {slug: e.id for slug in slugs if (e := await repo.by_slug(slug)) is not None}


async def make_program(api: httpx.AsyncClient, exercise_ids: dict[str, int]) -> list[int]:
    def day(name: str, slug: str) -> dict[str, Any]:
        planned = {"exercise_id": exercise_ids[slug], "sets": 3, "rep_min": 5, "rep_max": 5}
        return {"name": name, "exercises": [{**planned, "rest_seconds": 120}]}

    response = await api.post(
        "/v1/training/programs",
        json={
            "name": "A/B",
            "goal": "strength",
            "days": [day("A", "bench-press"), day("B", "back-squat")],
        },
    )
    assert response.status_code == 201, response.text
    program = response.json()
    await api.post(f"/v1/training/programs/{program['id']}/activate")
    return [d["id"] for d in program["days"]]


async def test_next_day_rotates_through_the_program(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    assert (await api.get("/v1/training/programs/active/next-day")).status_code == 404
    exercise_ids = await ids(sessionmaker, "bench-press", "back-squat")
    day_a, day_b = await make_program(api, exercise_ids)

    first = (await api.get("/v1/training/programs/active/next-day")).json()
    assert (first["day_id"], first["day_name"], first["open_workout_id"]) == (day_a, "A", None)
    assert [p["exercise"]["slug"] for p in first["planned"]] == ["bench-press"]

    # A workout following day A is open: A stays current, with that workout.
    started = (NOW - timedelta(hours=1)).isoformat()
    workout = (
        await api.put(
            f"/v1/training/workouts/{uuid.uuid4()}",
            json={"program_day_id": day_a, "started_at": started},
        )
    ).json()
    current = (await api.get("/v1/training/programs/active/next-day")).json()
    assert (current["day_id"], current["open_workout_id"]) == (day_a, workout["id"])

    # Finished: B is next; after B, A again.
    await api.post(f"/v1/training/workouts/{workout['id']}/finish")
    after_a = (await api.get("/v1/training/programs/active/next-day")).json()
    assert (after_a["day_id"], after_a["day_name"]) == (day_b, "B")
    b = (
        await api.put(f"/v1/training/workouts/{uuid.uuid4()}", json={"program_day_id": day_b})
    ).json()
    await api.post(f"/v1/training/workouts/{b['id']}/finish")
    again = (await api.get("/v1/training/programs/active/next-day")).json()
    assert again["day_id"] == day_a


async def test_redelivered_log_stores_its_sets_once(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport) as api_http,
        httpx.AsyncClient() as telegram_http,
        respx.mock(assert_all_called=False) as telegram_mock,
    ):
        send = telegram_mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))

        def bot() -> Dispatcher:
            """A fresh bot process: no memory of earlier deliveries."""
            api = ReadApi(api_http, "http://api", SecretStr(KEY))
            telegram = TelegramApi(telegram_http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
            training = TrainingCommands(
                api, MemoryStateStore(), lambda: NOW, ZoneInfo("Europe/Istanbul"), MSG
            )
            return Dispatcher(
                telegram, Commands(api, lambda: NOW, MSG), {CHAT}, MSG, features=[training]
            )

        update = Update.model_validate(message_update(501, CHAT, "/log bench 80x5x3"))
        await bot().handle(update)
        await bot().handle(update)  # Telegram redelivers after a crash

    async with sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(WorkoutSet))
        indexes = list(await session.scalars(select(WorkoutSet.set_index)))
    assert count == 3
    assert sorted(indexes) == [1, 2, 3]
    texts = [m["text"] for m in sent_messages(send)]
    assert texts == ["Logged Bench Press: 80 kg x 5, 5, 5. Workout volume 1,200 kg."] * 2


async def test_redis_state_store(redis: Redis) -> None:
    store = RedisStateStore(redis)
    assert await store.get("bot:test") is None
    await store.set("bot:test", "value", 60)
    assert await store.get("bot:test") == "value"
    assert 0 < await redis.ttl("bot:test") <= 60
    await store.delete("bot:test")
    assert await store.get("bot:test") is None


class LoseFirstStartAnswer(httpx.AsyncBaseTransport):
    """Forwards everything, but the first workout start reaches the API and its answer is lost,
    like a gym Wi-Fi drop after the request went out."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.lost = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        is_start = request.method == "PUT" and re.search(
            r"/workouts/[0-9a-f-]{36}$", request.url.path
        )
        if is_start and not self.lost:
            self.lost += 1
            raise httpx.ReadTimeout("answer lost", request=request)
        return response


async def test_start_retries_and_lost_answers_make_one_workout(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    transport = LoseFirstStartAnswer(httpx.ASGITransport(app=app))
    async with (
        httpx.AsyncClient(transport=transport) as api_http,
        httpx.AsyncClient() as telegram_http,
        respx.mock(assert_all_called=False) as telegram_mock,
    ):
        send = telegram_mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
        api = ReadApi(api_http, "http://api", SecretStr(KEY))
        telegram = TelegramApi(telegram_http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
        training = TrainingCommands(
            api, MemoryStateStore(), lambda: NOW, ZoneInfo("Europe/Istanbul"), MSG
        )
        bot = Dispatcher(
            telegram, Commands(api, lambda: NOW, MSG), {CHAT}, MSG, features=[training]
        )
        update = Update.model_validate(message_update(502, CHAT, "/log bench 80x5x3"))
        await bot.handle(update)  # the start's answer is lost: a friendly error
        await bot.handle(update)  # Telegram redelivers
        assert transport.lost == 1

        # A plain retry of the same start returns the same workout.
        start_id = client_id(f"tg:{CHAT}:502:start")
        again = await api.start_workout(start_id, NOW)
        assert (await api.start_workout(start_id, NOW + timedelta(minutes=5))).id == again.id

    async with sessionmaker() as session:
        workouts = list(await session.scalars(select(Workout)))
        sets = await session.scalar(select(func.count()).select_from(WorkoutSet))
    assert [w.client_id for w in workouts] == [start_id]
    assert workouts[0].id == again.id
    assert sets == 3
    texts = [m["text"] for m in sent_messages(send)]
    assert texts[-1] == "Logged Bench Press: 80 kg x 5, 5, 5. Workout volume 1,200 kg."
