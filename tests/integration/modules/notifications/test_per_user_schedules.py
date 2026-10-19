"""P8.5, ADR 0036: the worker's crons run per user, in each user's time zone and quiet hours."""

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.accounts import create_user
from tests.support.linked import link_chat
from tests.support.messages import NEUTRAL_EN as MSG
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, ok, sent_messages
from trainsync.integrations.telegram.client import TelegramApi
from trainsync.modules.coach.lines import MemoryRecentStore, load_pack
from trainsync.modules.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.notifications.checkin import CheckinDeps, run_checkin
from trainsync.modules.notifications.coach import CoachDeps, run_reminders
from trainsync.modules.training.models import Program, ProgramDay, ProgramExercise
from trainsync.modules.training.progression import Rules
from trainsync.modules.training.repository import ExerciseRepository, ProgramRepository

ISTANBUL, NEW_YORK = "Europe/Istanbul", "America/New_York"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def users(sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    istanbul = await create_user(sessionmaker, "ist@example.com", timezone=ISTANBUL)
    new_york = await create_user(sessionmaker, "nyc@example.com", timezone=NEW_YORK)
    await link_chat(sessionmaker, 1001, istanbul.id)
    await link_chat(sessionmaker, 1002, new_york.id, quiet_hours="00:00-00:00")
    return istanbul.id, new_york.id


@pytest.fixture
async def telegram() -> AsyncIterator[tuple[TelegramApi, respx.Route]]:
    async with httpx.AsyncClient() as http:
        with respx.mock(assert_all_called=False) as mock:
            send = mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
            yield TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM), send


async def test_each_user_gets_the_check_in_at_their_own_evening(
    sessionmaker: async_sessionmaker[AsyncSession],
    users: tuple[int, int],
    telegram: tuple[TelegramApi, respx.Route],
) -> None:
    istanbul, new_york = users
    api, send = telegram
    clock = Clock(datetime(2026, 10, 18, 18, 0, tzinfo=UTC))  # 21:00 Istanbul, 14:00 New York
    deps = CheckinDeps(sessionmaker, api, clock, MSG, make_settings(checkin_time="21:00"))
    assert await run_checkin(deps) == {istanbul: "sent_prompt", new_york: "nothing"}
    clock.now = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)  # 04:00 Istanbul, 21:00 New York
    assert await run_checkin(deps) == {istanbul: "nothing", new_york: "sent_prompt"}
    first, second = sent_messages(send)
    assert (first["chat_id"], second["chat_id"]) == (1001, 1002)
    # The New York prompt is about its own local day, 18 Oct.
    assert second["reply_markup"]["inline_keyboard"][0][0]["callback_data"].startswith(
        "ci:20261018:"
    )


async def _program(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> None:
    async with sessionmaker.begin() as session:
        bench = await ExerciseRepository(session, user_id).by_slug("bench-press")
        assert bench is not None
        repo = ProgramRepository(session, user_id)
        saved = await repo.add(
            Program(name="Push", goal="strength", days_per_week=1, weeks=4),
            [
                (
                    # Sunday 23:30 local: 18 Oct 2026 is a Sunday in both zones at the test times.
                    ProgramDay(day_index=0, name="Sunday", weekday=6, start_time=time(23, 30)),
                    [
                        ProgramExercise(
                            exercise_id=bench.id,
                            sets=1,
                            rep_min=5,
                            rep_max=5,
                            rest_seconds=60,
                            start_weight_kg=Decimal(40),
                        )
                    ],
                )
            ],
        )
        await repo.activate(saved.id)


async def test_quiet_hours_are_each_user_s(
    sessionmaker: async_sessionmaker[AsyncSession],
    users: tuple[int, int],
    telegram: tuple[TelegramApi, respx.Route],
) -> None:
    """23:00 local: the Istanbul user's quiet hours (default 23:00-07:00) hold the reminder;
    the New York user switched them off and gets theirs."""
    istanbul, new_york = users
    await _program(sessionmaker, istanbul)
    await _program(sessionmaker, new_york)
    api, send = telegram
    voice = CoachVoice(
        msg=MSG,
        mode=CoachMode(configured=False, soft=MemorySoftModeStore()),
        pack=load_pack(None),
        recent=MemoryRecentStore(),
        rng=random.Random(1),
    )
    settings = make_settings(quiet_hours="23:00-07:00")
    deps = CoachDeps(
        sessionmaker,
        api,
        Clock(datetime(2026, 10, 18, 20, 0, tzinfo=UTC)),
        voice,
        MSG,
        Rules(),
        settings,
    )
    assert (await run_reminders(deps))[istanbul] == "quiet"  # 23:00 Istanbul
    deps = CoachDeps(
        sessionmaker,
        api,
        Clock(datetime(2026, 10, 19, 3, 0, tzinfo=UTC)),
        voice,
        MSG,
        Rules(),
        settings,
    )
    assert (await run_reminders(deps))[new_york] == "sent"  # 23:00 New York, 30 min before
    assert [m["chat_id"] for m in sent_messages(send)] == [1002]
