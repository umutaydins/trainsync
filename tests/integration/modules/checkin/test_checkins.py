"""P6.9 against Postgres: the check-in API (idempotent PUT, body metric, summary = the
hand-computed fixture), the evening scheduler (once, not when answered, one reminder, safe across
restarts) and the conversation with the real API behind it (duplicate deliveries)."""

import json
import random
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.accounts import OWNER_ID
from tests.support.linked import link_chat, outcome_of
from tests.support.messages import NEUTRAL_EN as MSG
from tests.support.state import MemoryStateStore
from tests.support.telegram import (
    BOT_TOKEN,
    BOT_URL,
    TELEGRAM,
    error,
    message_update,
    ok,
    sent_messages,
)
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.entrypoints.bot.dispatcher import Commands, Dispatcher
from trainsync.integrations.telegram.client import TelegramApi, Update
from trainsync.modules.chat.checkin import CheckinFlow, prompt
from trainsync.modules.chat.links import ChatLinks
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.chat.training import TrainingCommands
from trainsync.modules.checkin.models import DailyCheckin
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.lines import MemoryRecentStore, load_packs
from trainsync.modules.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.notifications.checkin import CheckinDeps, run_checkin
from trainsync.modules.training.models import WorkoutSet
from trainsync.modules.training.repository import BodyMetricRepository

pytestmark = pytest.mark.integration

KEY = "test-api-key"
FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[3] / "fixtures" / "checkins.json").read_text(encoding="utf-8")
)
NOW = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)  # 18:00 in Istanbul, Sunday
CHAT = 42
ZONE = ZoneInfo("Europe/Istanbul")


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture
async def app(integration_settings: Settings, clock: Clock) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = clock
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api", headers={"X-API-Key": KEY}
    ) as client:
        yield client


async def make_program(api: httpx.AsyncClient, days: int = 3) -> dict[str, Any]:
    exercises = (await api.get("/v1/training/exercises", params={"q": "bench-press"})).json()
    bench = next(e for e in exercises["items"] if e["slug"] == "bench-press")
    planned = {"exercise_id": bench["id"], "sets": 3, "rep_min": 5, "rep_max": 5}
    body = {
        "name": "Full body",
        "goal": "strength",
        "days": [
            {"name": f"Day {n + 1}", "exercises": [{**planned, "rest_seconds": 120}]}
            for n in range(days)
        ],
    }
    program: dict[str, Any] = (await api.post("/v1/training/programs", json=body)).json()
    await api.post(f"/v1/training/programs/{program['id']}/activate")
    return program


# ---------------------------------------------------------------- API


async def test_put_is_idempotent_and_writes_the_body_metric(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    assert (await api.get("/v1/checkins/2026-10-18")).status_code == 404
    body = {"status": "done", "sleep_hours": 7.5, "energy_1_5": 4, "body_weight_kg": 78.4}
    first = await api.put("/v1/checkins/2026-10-18", json=body)
    assert first.status_code == 201, first.text
    again = await api.put("/v1/checkins/2026-10-18", json=body)
    assert again.status_code == 200
    assert {k: v for k, v in again.json().items() if k != "updated_at"} == {
        k: v for k, v in first.json().items() if k != "updated_at"
    }
    assert first.json()["sleep_hours"] == 7.5
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(DailyCheckin)) == 1
        metric = await BodyMetricRepository(session, OWNER_ID).latest()
    assert metric is not None
    assert (metric.date, float(metric.weight_kg)) == (date(2026, 10, 18), 78.4)

    # A correction replaces every field; the body metric stays.
    fixed = await api.put("/v1/checkins/2026-10-18", json={"status": "partial"})
    assert fixed.status_code == 200
    assert (fixed.json()["status"], fixed.json()["body_weight_kg"]) == ("partial", None)
    got = (await api.get("/v1/checkins/2026-10-18")).json()
    assert got["status"] == "partial"
    async with sessionmaker() as session:
        assert await BodyMetricRepository(session, OWNER_ID).latest() is not None


async def test_put_validation(api: httpx.AsyncClient) -> None:
    for body in (
        {"status": "maybe"},
        {"status": "done", "energy_1_5": 6},
        {"status": "done", "sleep_hours": 25},
        {"status": "done", "body_weight_kg": 0},
    ):
        assert (await api.put("/v1/checkins/2026-10-18", json=body)).status_code == 422
    missing = await api.put("/v1/checkins/2026-10-18", json={"status": "done", "workout_id": 999})
    assert missing.status_code == 400


async def test_list_and_summary_match_the_fixture(api: httpx.AsyncClient) -> None:
    for day, status in FIXTURE["days"].items():
        response = await api.put(f"/v1/checkins/{day}", json={"status": status})
        assert response.status_code == 201
    await make_program(api, FIXTURE["days_per_week"])

    listed = await api.get("/v1/checkins", params={"from": "2026-10-01", "to": "2026-10-07"})
    assert [i["date"] for i in listed.json()["items"]] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
    ]
    default = (await api.get("/v1/checkins")).json()
    assert (default["from"], default["to"]) == ("2026-07-27", "2026-10-18")  # 12 weeks

    for case in FIXTURE["cases"]:
        params = {"from": case["from"], "to": case["to"]}
        summary = (await api.get("/v1/checkins/summary", params=params)).json()
        assert summary["planned_days"] == case["planned"]
        assert summary["planned_days_done"] == case["done"]
        assert summary["adherence"] == case["adherence"]
        assert summary["current_streak"] == case["current_streak"]
        assert summary["longest_streak"] == case["longest_streak"]
        assert summary["counts"] == case["counts"]
        assert [[w["week_start"], w["planned"], w["done"]] for w in summary["weeks"]] == case[
            "weeks"
        ]
        assert summary["days_per_week"] == 3
    # Default range: this ISO week and the three before it.
    default_summary = (await api.get("/v1/checkins/summary")).json()
    assert (default_summary["from"], default_summary["to"]) == ("2026-09-21", "2026-10-18")
    assert default_summary["today"] == "2026-10-18"


async def test_summary_without_a_program_and_bad_ranges(api: httpx.AsyncClient) -> None:
    summary = (await api.get("/v1/checkins/summary")).json()
    assert (summary["adherence"], summary["planned_days"], summary["days_per_week"]) == (
        None,
        0,
        None,
    )
    for params in ({"from": "2026-10-18", "to": "2026-10-01"}, {"from": "2024-01-01"}):
        assert (await api.get("/v1/checkins", params=params)).status_code == 400


# ---------------------------------------------------------------- scheduler


async def tick(deps: CheckinDeps) -> str:
    return outcome_of(await run_checkin(deps))


@pytest.fixture
async def scheduler(
    sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> AsyncIterator[tuple[CheckinDeps, respx.Route]]:
    async with httpx.AsyncClient() as http:
        with respx.mock(assert_all_called=False) as mock:
            send = mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
            telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
            await link_chat(sessionmaker, CHAT, timezone=ZONE.key)
            deps = CheckinDeps(
                sessionmaker=sessionmaker,
                telegram=telegram,
                clock=clock,
                msg=MSG,
                settings=make_settings(checkin_time="21:00", checkin_reminder_minutes=90),
            )
            yield deps, send


async def test_prompt_once_then_one_reminder(
    scheduler: tuple[CheckinDeps, respx.Route], clock: Clock
) -> None:
    deps, send = scheduler
    clock.now = datetime(2026, 10, 18, 17, 55, tzinfo=UTC)  # 20:55 local
    assert await tick(deps) == "nothing"
    clock.now = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    assert await tick(deps) == "sent_prompt"
    assert await tick(deps) == "nothing"  # a second tick, or a restarted worker
    clock.now = datetime(2026, 10, 18, 19, 25, tzinfo=UTC)
    assert await tick(deps) == "nothing"
    clock.now = datetime(2026, 10, 18, 19, 30, tzinfo=UTC)
    assert await tick(deps) == "sent_reminder"
    clock.now = datetime(2026, 10, 18, 20, 55, tzinfo=UTC)
    assert await tick(deps) == "nothing"
    [prompt_msg, reminder_msg] = sent_messages(send)
    assert prompt_msg["text"] == "Daily check-in: did you train today?"
    assert prompt_msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == (
        "ci:20261018:0:s:done"
    )
    assert reminder_msg["text"].startswith("Reminder:")
    # The next local day starts over.
    clock.now = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
    assert await tick(deps) == "sent_prompt"


async def test_no_prompt_or_reminder_once_answered(
    scheduler: tuple[CheckinDeps, respx.Route], clock: Clock, api: httpx.AsyncClient
) -> None:
    deps, send = scheduler
    await api.put("/v1/checkins/2026-10-18", json={"status": "rest"})
    clock.now = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    assert await tick(deps) == "nothing"
    await api.put("/v1/checkins/2026-10-19", json={"status": "rest"})
    clock.now = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
    assert await tick(deps) == "nothing"
    assert send.call_count == 0


async def test_answer_after_the_prompt_stops_the_reminder(
    scheduler: tuple[CheckinDeps, respx.Route], clock: Clock, api: httpx.AsyncClient
) -> None:
    deps, send = scheduler
    clock.now = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    assert await tick(deps) == "sent_prompt"
    await api.put("/v1/checkins/2026-10-18", json={"status": "done"})
    clock.now = datetime(2026, 10, 18, 20, 0, tzinfo=UTC)
    assert await tick(deps) == "nothing"
    assert send.call_count == 1


async def test_failed_send_is_retried_on_the_next_tick(
    scheduler: tuple[CheckinDeps, respx.Route], clock: Clock
) -> None:
    deps, send = scheduler
    clock.now = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    send.mock(side_effect=[error(400, "chat not found"), ok({})])
    assert await tick(deps) == "failed"
    clock.now += timedelta(minutes=5)
    assert await tick(deps) == "sent_prompt"
    send.mock(side_effect=httpx.ReadTimeout("lost"))
    clock.now = datetime(2026, 10, 18, 19, 35, tzinfo=UTC)
    assert await tick(deps) == "unknown"  # may have arrived: keep the claim
    clock.now += timedelta(minutes=5)
    assert await tick(deps) == "nothing"


async def test_disabled_without_telegram(
    sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> None:
    deps = CheckinDeps(sessionmaker, None, clock, MSG, make_settings())
    assert await run_checkin(deps) == {}


# ---------------------------------------------------------------- conversation over the real API


async def test_duplicate_deliveries_store_one_check_in_and_one_set_each(
    app: FastAPI, api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await make_program(api)
    transport = httpx.ASGITransport(app=app)
    store = MemoryStateStore()
    async with (
        httpx.AsyncClient(transport=transport) as api_http,
        httpx.AsyncClient() as telegram_http,
        respx.mock(assert_all_called=False) as telegram_mock,
    ):
        send = telegram_mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
        telegram_mock.post(f"{BOT_URL}/answerCallbackQuery").mock(return_value=ok(True))
        telegram_mock.post(f"{BOT_URL}/editMessageReplyMarkup").mock(return_value=ok(True))
        bot_api = ReadApi(api_http, "http://api", SecretStr(KEY))
        telegram = TelegramApi(telegram_http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
        clock = lambda: NOW  # noqa: E731
        await link_chat(sessionmaker, CHAT, timezone=ZONE.key)
        dispatcher = Dispatcher(
            telegram,
            Commands(bot_api, clock, MSG),
            ChatLinks(bot_api, clock, ttl_s=0),
            MSG,
            features=[
                CheckinFlow(bot_api, store, clock, ZONE, MSG),
                TrainingCommands(bot_api, store, clock, ZONE, MSG),
            ],
        )

        async def deliver(update: dict[str, Any], times: int = 2) -> None:
            for _ in range(times):
                await dispatcher.handle(Update.model_validate(update))

        def press(update_id: int, data: str) -> dict[str, Any]:
            return {
                "update_id": update_id,
                "callback_query": {
                    "id": f"cq{update_id}",
                    "data": data,
                    "message": {"message_id": 1, "chat": {"id": CHAT}},
                },
            }

        await deliver(message_update(1, CHAT, "/report"), times=1)
        await deliver(press(2, "ci:20261018:1:s:done"))  # double tap / redelivery
        await deliver(message_update(3, CHAT, "80x5x3"))  # redelivered text answer
        await deliver(press(4, "ci:20261018:3:k"))  # skip the scale question
        await deliver(press(5, "ci:20261018:4:k"))
        await deliver(press(6, "ci:20261018:5:e:3"))
        texts = [m["text"] for m in sent_messages(send)]

    async with sessionmaker() as session:
        checkins = list(await session.scalars(select(DailyCheckin)))
        sets = list(await session.scalars(select(WorkoutSet)))
    assert [(c.date, c.status, c.energy_1_5) for c in checkins] == [(date(2026, 10, 18), "done", 3)]
    assert checkins[0].workout_id is not None
    assert sorted((s.set_index, float(s.weight_kg), s.reps) for s in sets) == [
        (1, 80.0, 5),
        (2, 80.0, 5),
        (3, 80.0, 5),
    ]
    assert texts[-1].startswith("Check-in saved for 18 Oct: ✅ Done\nWorkout: 3 sets · 1,200 kg")
    assert texts[-1].endswith("Check-in streak: 1 days")


async def test_in_max_the_prompt_swears_read_at_send_time(
    scheduler: tuple[CheckinDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """ADR 0032: the chat chose /swear max; the savage coach is on: the prompt gets an opener."""
    deps, send = scheduler
    packs = load_packs(None)
    voice = CoachVoice(
        msg=MSG,
        mode=CoachMode(configured=True, soft=MemorySoftModeStore()),
        pack=packs["en"],
        recent=MemoryRecentStore(),
        rng=random.Random(1),
        packs=packs,
    )
    deps = replace(deps, voice=voice)
    await link_chat(sessionmaker, CHAT, lang="en", profanity="max")
    clock.now = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    assert await tick(deps) == "sent_prompt"
    opener, rest = sent_messages(send)[-1]["text"].split("\n", 1)
    assert opener in packs["en"].max[Category.MAX_OPENER]
    assert rest.startswith(prompt(MSG, date(2026, 10, 18)).text.split("\n")[0])
