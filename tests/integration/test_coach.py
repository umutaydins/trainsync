"""P6.11: timed coach messages against Postgres with a fake clock and a fake Telegram API —
the reminder cron (before, now, +30, +90, missed; stops on a started workout; quiet hours; never
twice) and the workout events (start, under target once, rest over, verdict) (ADR 0030)."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.

import random
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, error, ok, sent_messages
from trainsync.bot.common import client_id
from trainsync.bot.messages import PACKS, Key, Messages, messages_for
from trainsync.bot.telegram import TelegramApi
from trainsync.coach.categories import Category
from trainsync.coach.lines import MemoryRecentStore, load_pack, load_packs
from trainsync.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.coach.savage_tr import LINES
from trainsync.coach.voice import CoachVoice
from trainsync.core.settings import BotLang
from trainsync.db.models import Notification, Program, ProgramDay, ProgramExercise
from trainsync.db.repositories.chat_settings import ChatSettingsRepository
from trainsync.db.repositories.training import (
    ExerciseRepository,
    ProgramRepository,
    SetValues,
    WorkoutRepository,
)
from trainsync.notify.coach import (
    CoachDeps,
    rest_over,
    run_reminders,
    set_logged,
    workout_finished,
    workout_started,
)
from trainsync.training.progression import Rules

pytestmark = pytest.mark.integration

ZONE = ZoneInfo("Europe/Istanbul")
CHAT = 4242
MONDAY_18 = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)  # Monday 18:00 in Istanbul
MSG = Messages(PACKS["neutral", "tr"])


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def local(self, hh: int, mm: int, days: int = 0) -> None:
        self.now = (datetime(2026, 10, 19, hh, mm, tzinfo=ZONE) + timedelta(days=days)).astimezone(
            UTC
        )


@pytest.fixture
def clock() -> Clock:
    return Clock(MONDAY_18)


def voice(savage: bool) -> CoachVoice:
    msg = Messages(PACKS["hardcore" if savage else "neutral", "tr"])
    return CoachVoice(
        msg=msg,
        mode=CoachMode(configured=savage, soft=MemorySoftModeStore()),
        pack=load_pack(None),
        recent=MemoryRecentStore(),
        rng=random.Random(4),
    )


@pytest.fixture
async def coach(
    sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> AsyncIterator[tuple[CoachDeps, respx.Route]]:
    async with httpx.AsyncClient() as http:
        with respx.mock(assert_all_called=False) as mock:
            send = mock.post(f"{BOT_URL}/sendMessage").mock(return_value=ok({}))
            deps = CoachDeps(
                sessionmaker=sessionmaker,
                telegram=TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM),
                chat_id=CHAT,
                clock=clock,
                voice=voice(savage=False),
                msg=MSG,
                zone=ZONE,
                default_start=time(18, 0),
                quiet=(time(23, 0), time(7, 0)),
                rules=Rules(),
            )
            yield deps, send


async def program(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    weekday: int | None = 0,
    start: time | None = time(18, 0),
    sets: int = 2,
    weight: str | None = "80",
) -> tuple[int, int]:
    """An active 1-day program on `weekday` with bench press; (day id, exercise id)."""
    async with sessionmaker.begin() as session:
        bench = await ExerciseRepository(session).by_slug("bench-press")
        assert bench is not None
        repo = ProgramRepository(session)
        saved = await repo.add(
            Program(name="Push", goal="strength", days_per_week=1, weeks=4),
            [
                (
                    ProgramDay(day_index=0, name="Push A", weekday=weekday, start_time=start),
                    [
                        ProgramExercise(
                            exercise_id=bench.id,
                            sets=sets,
                            rep_min=5,
                            rep_max=5,
                            rest_seconds=120,
                            start_weight_kg=Decimal(weight) if weight else None,
                        )
                    ],
                )
            ],
        )
        await repo.activate(saved.id)
        tree = await repo.tree(saved.id)
        assert tree is not None
        return tree.days[0][0].id, bench.id


def texts(send: respx.Route) -> list[str]:
    return [m["text"] for m in sent_messages(send)]


# ---------------------------------------------------------------- reminders


async def test_every_stage_once_in_order(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    await program(sessionmaker)
    outcomes = []
    for hh, mm in [(17, 15), (17, 30), (17, 31), (18, 0), (18, 5), (18, 30), (19, 30), (21, 0)]:
        clock.local(hh, mm)
        outcomes.append(await run_reminders(deps))
    assert outcomes == [
        "nothing",
        "sent",  # 30 min before
        "nothing",  # already sent: a second tick or a restarted worker
        "sent",  # at start
        "nothing",
        "sent",  # +30
        "sent",  # +90
        "sent",  # +180: missed
    ]
    assert texts(send) == [
        MSG(Key.COACH_REMINDER_BEFORE, day="Push A", time="18:00"),
        MSG(Key.COACH_REMINDER_NOW, day="Push A", time="18:00"),
        MSG(Key.COACH_NUDGE, day="Push A", time="18:00"),
        MSG(Key.COACH_NUDGE, day="Push A", time="18:00"),
        MSG(Key.COACH_MISSED, day="Push A"),
    ]
    clock.local(18, 0, days=1)  # Tuesday: not a training day
    assert await run_reminders(deps) == "no_plan"


async def test_a_started_workout_stops_the_reminders(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    await program(sessionmaker)
    clock.local(18, 0)
    assert await run_reminders(deps) == "sent"
    async with sessionmaker.begin() as session:
        await WorkoutRepository(session).start(uuid.uuid4(), clock.now + timedelta(minutes=5))
    for hh, mm in [(18, 30), (19, 30), (21, 0)]:
        clock.local(hh, mm)
        assert await run_reminders(deps) == "started"
    assert len(texts(send)) == 1


async def test_quiet_hours_send_nothing_and_never_late(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    await program(sessionmaker, start=time(23, 15))
    clock.local(22, 45)
    assert await run_reminders(deps) == "sent"  # before: still outside quiet hours
    clock.local(23, 15)
    assert await run_reminders(deps) == "quiet"
    clock.local(23, 16)
    assert await run_reminders(deps) == "quiet"
    clock.local(7, 0, days=1)  # quiet hours over: the night's stages are long past
    assert await run_reminders(deps) == "no_plan"
    assert len(texts(send)) == 1
    async with sessionmaker() as session:
        claimed = await session.scalar(select(func.count()).select_from(Notification))
    assert claimed == 1  # a quiet stage is not claimed, so nothing is "owed" later


async def test_default_schedule_and_start_time(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, _ = coach
    await program(sessionmaker, weekday=None, start=None)  # 1 day a week → Monday, 18:00
    clock.local(17, 30)
    assert await run_reminders(deps) == "sent"


async def test_a_failed_send_is_retried_on_the_next_tick(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    await program(sessionmaker)
    send.side_effect = [error(400, "Bad Request: chat not found"), ok({})]
    clock.local(18, 0)
    assert await run_reminders(deps) == "failed"
    clock.local(18, 1)
    assert await run_reminders(deps) == "sent"


async def test_savage_reminders_are_a_fact_line_and_a_savage_line(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    deps = replace(deps, voice=voice(savage=True))
    await program(sessionmaker)
    clock.local(18, 30)
    assert await run_reminders(deps) == "sent"
    fact, line = texts(send)[0].split("\n", 1)
    assert fact == "Push A · 18:00"
    assert any(line.startswith(roast) for roast in LINES[Category.ESCALATION]), line


async def test_disabled_without_telegram(
    coach: tuple[CoachDeps, respx.Route], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    deps, _ = coach
    assert await run_reminders(replace(deps, telegram=None)) == "disabled"


# ---------------------------------------------------------------- workout events


async def start(
    sessionmaker: async_sessionmaker[AsyncSession], at: datetime, day_id: int | None, cid: uuid.UUID
) -> int:
    async with sessionmaker.begin() as session:
        workout, _ = await WorkoutRepository(session).start(cid, at, day_id)
        return workout.id


async def log(
    sessionmaker: async_sessionmaker[AsyncSession],
    workout_id: int,
    exercise_id: int,
    index: int,
    reps: int,
    weight: str,
    at: datetime,
) -> int:
    async with sessionmaker.begin() as session:
        result = await WorkoutRepository(session).put_set(
            workout_id, uuid.uuid4(), SetValues(exercise_id, index, reps, Decimal(weight), at)
        )
        assert result is not None
        return result[0].id


async def test_start_under_target_rest_and_a_bad_verdict(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    day_id, bench = await program(sessionmaker, sets=3)
    workout = await start(sessionmaker, clock.now, day_id, uuid.uuid4())
    assert await workout_started(deps, workout) == "sent"
    assert await workout_started(deps, workout) == "duplicate"

    first = await log(sessionmaker, workout, bench, 1, 3, "80", clock.now)  # 3 < 5 reps
    assert await set_logged(deps, first, None) == "sent"
    clock.now += timedelta(seconds=60)
    second = await log(sessionmaker, workout, bench, 2, 5, "70", clock.now)  # lighter than 80
    assert await set_logged(deps, second, None) == "duplicate"  # once per exercise

    clock.now += timedelta(seconds=121)
    assert await rest_over(deps, first) == "superseded"  # a newer set exists
    assert await rest_over(deps, second) == "sent"
    clock.now += timedelta(minutes=10)
    assert await rest_over(deps, second) == "late"

    async with sessionmaker.begin() as session:
        await WorkoutRepository(session).finish(workout, clock.now)
    assert await workout_finished(deps, workout) == "sent"
    assert await workout_finished(deps, workout) == "duplicate"
    start_text, under_text, rest_text, done_text = texts(send)
    assert start_text == MSG(Key.COACH_WORKOUT_START, day="Push A")
    assert under_text == MSG(
        Key.COACH_UNDER_TARGET, exercise="Bench Press", done="80 kg x 3", target="80 kg x 5"
    )
    assert rest_text == MSG(Key.COACH_REST_OVER)
    assert done_text.endswith(MSG(Key.COACH_DONE_BAD, missing=1))


async def test_a_complete_workout_gets_the_good_verdict_and_no_rest_after_the_last_set(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    day_id, bench = await program(sessionmaker, sets=2)
    workout = await start(sessionmaker, clock.now, day_id, uuid.uuid4())
    await log(sessionmaker, workout, bench, 1, 5, "80", clock.now)
    clock.now += timedelta(seconds=150)
    last = await log(sessionmaker, workout, bench, 2, 5, "80", clock.now)
    assert await set_logged(deps, last, None) == "ok"
    clock.now += timedelta(seconds=120)
    assert await rest_over(deps, last) == "all_done"
    async with sessionmaker.begin() as session:
        await WorkoutRepository(session).finish(workout, clock.now)
    assert await workout_finished(deps, workout) == "sent"
    assert texts(send)[-1].endswith(MSG(Key.COACH_DONE_GOOD))


async def test_check_in_workouts_get_no_live_messages(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    deps, send = coach
    day_id, bench = await program(sessionmaker)
    checkin_id = client_id("checkin:2026-10-19:workout")
    workout = await start(sessionmaker, clock.now, day_id, checkin_id)
    assert await workout_started(deps, workout) == "skipped"
    logged = await log(sessionmaker, workout, bench, 1, 1, "40", clock.now)
    assert await set_logged(deps, logged, None) == "skipped"
    async with sessionmaker.begin() as session:
        await WorkoutRepository(session).finish(workout, clock.now)
    assert await workout_finished(deps, workout) == "skipped"
    assert texts(send) == []


# ---------------------------------------------------------------- the chat's language (P6.12)


async def store_lang(sessionmaker: async_sessionmaker[AsyncSession], lang: BotLang) -> None:
    async with sessionmaker.begin() as session:
        await ChatSettingsRepository(session).set_lang(CHAT, lang, MONDAY_18)


@pytest.mark.parametrize("savage", [False, True])
async def test_the_worker_speaks_the_language_stored_for_the_chat(
    coach: tuple[CoachDeps, respx.Route],
    clock: Clock,
    sessionmaker: async_sessionmaker[AsyncSession],
    savage: bool,
) -> None:
    """BOT_LANG is Turkish, the chat chose English with /lang: the reminder is English, read at
    send time (ADR 0031)."""
    deps, send = coach
    tone = "hardcore" if savage else "neutral"
    msg = messages_for(make_settings(bot_lang="tr", bot_tone=tone))
    packs = load_packs(None)
    deps = replace(
        deps,
        msg=msg,
        voice=CoachVoice(
            msg=msg,
            mode=CoachMode(configured=savage, soft=MemorySoftModeStore()),
            pack=packs["tr"],
            recent=MemoryRecentStore(),
            rng=random.Random(4),
            packs=packs,
        ),
    )
    await program(sessionmaker)
    clock.local(17, 30)
    await store_lang(sessionmaker, "en")
    assert await run_reminders(deps) == "sent"
    english = texts(send)[-1]
    if savage:
        fact, line = english.split("\n", 1)
        assert fact == "Push A · 18:00"
        assert any(line.startswith(x) for x in packs["en"].lines[Category.REMINDER_BEFORE]), line
    else:
        en = Messages(PACKS["neutral", "en"])
        assert english == en(Key.COACH_REMINDER_BEFORE, day="Push A", time="18:00")
    await store_lang(sessionmaker, "tr")  # switched back: the next stage is Turkish again
    clock.local(18, 0)
    assert await run_reminders(deps) == "sent"
    if not savage:
        assert texts(send)[-1] == MSG(Key.COACH_REMINDER_NOW, day="Push A", time="18:00")
