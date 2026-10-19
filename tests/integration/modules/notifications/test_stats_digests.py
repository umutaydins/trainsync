"""P8.11: the weekly (Monday) and monthly (1st) progress digests, per user and time zone."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.accounts import create_user
from tests.support.linked import link_chat
from tests.support.messages import NEUTRAL_EN as MSG
from tests.support.stats_data import Lift, Seeder
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, ok, sent_messages
from trainsync.integrations.telegram.client import TelegramApi
from trainsync.modules.notifications.digest import DigestDeps, run_digests
from trainsync.modules.users.settings import UserSettingsRepository

ISTANBUL, NEW_YORK = "Europe/Istanbul", "America/New_York"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class Users:
    istanbul: int
    new_york: int
    idle: int


async def _train(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> None:
    async with sessionmaker.begin() as session:
        seed = Seeder(session, user_id)
        await seed.workout(datetime(2026, 10, 21, 16, tzinfo=UTC), [Lift("bench-press", 5, 80)])
        await seed.workout(datetime(2026, 10, 14, 16, tzinfo=UTC), [Lift("bench-press", 5, 70)])


@pytest.fixture
async def users(sessionmaker: async_sessionmaker[AsyncSession]) -> Users:
    istanbul = await create_user(sessionmaker, "ist@example.com", timezone=ISTANBUL)
    new_york = await create_user(sessionmaker, "nyc@example.com", timezone=NEW_YORK)
    idle = await create_user(sessionmaker, "idle@example.com", timezone=ISTANBUL)
    for n, account in enumerate((istanbul, new_york, idle), start=1):
        await link_chat(sessionmaker, 1000 + n, account.id)
    await _train(sessionmaker, istanbul.id)
    await _train(sessionmaker, new_york.id)
    return Users(istanbul.id, new_york.id, idle.id)


@pytest.fixture
async def telegram() -> AsyncIterator[tuple[TelegramApi, respx.Route]]:
    async with httpx.AsyncClient() as http:
        with respx.mock(assert_all_called=False) as mock:
            send = mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
            yield TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM), send


async def _set(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, **changes: object
) -> None:
    async with sessionmaker.begin() as session:
        await UserSettingsRepository(session, user_id).update(
            changes, datetime(2026, 10, 25, tzinfo=UTC)
        )


def _deps(
    sessionmaker: async_sessionmaker[AsyncSession], api: TelegramApi, clock: Clock, redis: Redis
) -> DigestDeps:
    settings = make_settings(quiet_hours="23:00-07:00")
    return DigestDeps(sessionmaker, api, clock, MSG, settings, redis)


async def test_monday_morning_sends_last_week_once_in_each_zone(
    sessionmaker: async_sessionmaker[AsyncSession],
    users: Users,
    telegram: tuple[TelegramApi, respx.Route],
    redis: Redis,
) -> None:
    api, send = telegram
    clock = Clock(datetime(2026, 10, 26, 6, 0, tzinfo=UTC))  # Mon 09:00 Istanbul, 02:00 NY
    deps = _deps(sessionmaker, api, clock, redis)
    outcomes = await run_digests(deps)
    assert outcomes == {users.istanbul: ["sent"], users.new_york: [], users.idle: ["empty"]}
    assert await run_digests(deps) == {
        users.istanbul: ["duplicate"],
        users.new_york: [],
        users.idle: ["duplicate"],
    }
    clock.now = datetime(2026, 10, 26, 13, 0, tzinfo=UTC)  # 09:00 in New York
    assert (await run_digests(deps))[users.new_york] == ["sent"]
    first, second = sent_messages(send)
    assert first["chat_id"] == 1001
    assert first["text"].startswith("Your week (19-25 Oct)")
    assert "Workouts 1 · sets 1 · 400 kg" in first["text"]
    assert second["chat_id"] == 1002


async def test_quiet_hours_hold_the_digest_and_the_first_sends_the_month(
    sessionmaker: async_sessionmaker[AsyncSession],
    users: Users,
    telegram: tuple[TelegramApi, respx.Route],
    redis: Redis,
) -> None:
    api, send = telegram
    await _set(sessionmaker, users.istanbul, quiet_hours="08:00-10:00")
    clock = Clock(datetime(2026, 11, 1, 6, 0, tzinfo=UTC))  # Sun 1 Nov, 09:00 Istanbul
    deps = _deps(sessionmaker, api, clock, redis)
    assert (await run_digests(deps))[users.istanbul] == ["quiet"]
    clock.now = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)  # 10:30, quiet hours over
    assert (await run_digests(deps))[users.istanbul] == ["sent"]
    (message,) = [m for m in sent_messages(send) if m["chat_id"] == 1001]
    assert message["text"].startswith("Your month (1-31 Oct)")
    assert date(2026, 11, 1).weekday() == 6  # a Sunday: no weekly digest owed


async def test_off_for_a_user_who_switched_it_off(
    sessionmaker: async_sessionmaker[AsyncSession],
    users: Users,
    telegram: tuple[TelegramApi, respx.Route],
    redis: Redis,
) -> None:
    api, _ = telegram
    await _set(sessionmaker, users.istanbul, stats_digest_enabled=False)
    deps = _deps(sessionmaker, api, Clock(datetime(2026, 10, 26, 6, 0, tzinfo=UTC)), redis)
    assert (await run_digests(deps))[users.istanbul] == ["disabled"]
