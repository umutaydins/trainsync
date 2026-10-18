"""P6.11: the coach in chat — pain guard, savage triggers, soft mode — against the fake Telegram
API and the stubbed trainsync API (ADR 0030)."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import random
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.support.bot_api import API, FakeApi, install, planned
from tests.support.state import MemoryStateStore
from tests.support.telegram import (
    BOT_TOKEN,
    BOT_URL,
    TELEGRAM,
    SleepRecorder,
    message_update,
    ok,
    sent_messages,
)
from trainsync.bot.checkin import CheckinFlow
from trainsync.bot.coach import CoachFeature
from trainsync.bot.handlers import Commands, Dispatcher
from trainsync.bot.messages import PACKS, Key, Messages, NeutralKey
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi, Update
from trainsync.coach.categories import Category
from trainsync.coach.guardrails import violations
from trainsync.coach.lines import MemoryRecentStore, load_pack
from trainsync.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.coach.savage_tr import LINES
from trainsync.coach.voice import CoachVoice

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)  # Monday 12:00 in Istanbul
ZONE = ZoneInfo("Europe/Istanbul")
CHAT = 42
TR_HARD = Messages(PACKS["hardcore", "tr"])


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{BOT_URL}/sendMessage", name="send").mock(return_value=ok({}))
        yield mock


@pytest.fixture
def fake(router: respx.MockRouter) -> FakeApi:
    return install(router, lambda: NOW)


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def soft() -> MemorySoftModeStore:
    return MemorySoftModeStore()


class Assistant:
    """Stands in for the LLM: records what reached it."""

    def __init__(self) -> None:
        self.questions: list[str] = []

    async def __call__(self, chat_id: int, text: str) -> str:
        self.questions.append(text)
        return "assistant answer"


@pytest.fixture
def assistant() -> Assistant:
    return Assistant()


def voice(soft: MemorySoftModeStore, *, savage: bool = True, seed: int = 5) -> CoachVoice:
    return CoachVoice(
        msg=TR_HARD,
        mode=CoachMode(configured=savage, soft=soft),
        pack=load_pack(None),
        recent=MemoryRecentStore(),
        rng=random.Random(seed),
    )


def make(
    http: httpx.AsyncClient,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    *,
    savage: bool = True,
) -> Dispatcher:
    telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM, sleep=SleepRecorder())
    api = ReadApi(http, API, SecretStr("bot-key"))
    clock = lambda: NOW  # noqa: E731
    coach_voice = voice(soft, savage=savage)
    store = MemoryStateStore()
    return Dispatcher(
        telegram,
        Commands(api, clock, TR_HARD),
        {CHAT},
        TR_HARD,
        assistant,
        features=[
            CheckinFlow(api, store, clock, ZONE, TR_HARD, coach_voice),
            CoachFeature(api, coach_voice, soft, clock, ZONE, TR_HARD, time(18, 0)),
        ],
    )


async def say(dispatcher: Dispatcher, router: respx.MockRouter, text: str, update_id: int) -> str:
    await dispatcher.handle(Update.model_validate(message_update(update_id, CHAT, text)))
    return [m["text"] for m in sent_messages(router["send"])][-1]


ROASTS = {line for c in Category for line in LINES[c]}


def has_roast(text: str) -> bool:
    return any(line in text for line in ROASTS)


@pytest.mark.parametrize(
    "text",
    [
        "canım istemiyor, dizim ağrıyor",
        "yarın yaparım, göğsüm ağrıyor",
        "başım dönüyor bugün gitmeyeceğim",
        "hastayım",
        "chest pain, I'll do it tomorrow",
    ],
)
async def test_pain_never_gets_a_roast_or_reaches_the_assistant(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    text: str,
) -> None:
    reply = await say(make(http, soft, assistant), router, text, 1)
    assert reply == TR_HARD.neutral(NeutralKey.SAFETY_PAIN)
    assert not has_roast(reply)
    assert assistant.questions == []


async def test_an_excuse_gets_a_roast_and_one_action_for_today(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    fake.with_program(11, planned(20, 3, 5, 5, 80.0))
    reply = await say(make(http, soft, assistant), router, "canım istemiyor bugün", 1)
    roast, action = reply.split("\n")[0], reply.split("\n")[-1]
    assert any(roast.startswith(line) for line in LINES[Category.EXCUSE])
    assert action == TR_HARD(Key.COACH_ACTION_PLANNED, day="Upper A", time="18:00")
    assert violations(reply) == []
    assert assistant.questions == []


async def test_an_excuse_without_a_program_gets_the_fallback_action(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    reply = await say(make(http, soft, assistant), router, "yarın yaparım", 1)
    assert reply.endswith(TR_HARD(Key.COACH_ACTION_FALLBACK))


async def test_a_craving_gets_the_neutral_food_line_never_a_roast(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    reply = await say(make(http, soft, assistant), router, "canım tatlı çekti", 1)
    assert reply == TR_HARD.neutral(NeutralKey.FOOD_CRAVING, remaining="2600 kcal")
    assert not has_roast(reply)
    fake.kcal_target = None
    reply = await say(make(http, soft, assistant), router, "akşam pizza yiyeceğim", 2)
    assert reply == TR_HARD.neutral(NeutralKey.FOOD_CRAVING_NO_TARGET)


async def test_without_savage_excuses_go_to_the_assistant(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    reply = await say(make(http, soft, assistant, savage=False), router, "canım istemiyor", 1)
    assert reply == "assistant answer"
    assert assistant.questions == ["canım istemiyor"]


async def test_soft_mode_turns_the_roasts_off_and_sert_back_on(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    dispatcher = make(http, soft, assistant)
    assert await say(dispatcher, router, "/yumusak", 1) == TR_HARD(Key.COACH_SOFT_ON)
    assert soft.soft
    assert await say(dispatcher, router, "canım istemiyor", 2) == "assistant answer"
    assert await say(dispatcher, router, "/sert", 3) == TR_HARD(Key.COACH_SOFT_OFF)
    assert not soft.soft
    assert has_roast(await say(dispatcher, router, "canım istemiyor", 4))
    # Pain is answered the same way in soft mode too.
    await soft.soften()
    assert await say(dispatcher, router, "dizim ağrıyor", 5) == TR_HARD.neutral(
        NeutralKey.SAFETY_PAIN
    )


async def test_rotation_across_messages(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    dispatcher = make(http, soft, assistant)
    roasts = []
    for update_id in range(1, 10):
        reply = await say(dispatcher, router, "canım istemiyor", update_id)
        roasts.append(next(line for line in LINES[Category.EXCUSE] if reply.startswith(line)))
    assert len(set(roasts)) == len(roasts)  # 9 excuse lines, none repeated
