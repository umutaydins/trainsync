"""P6.11, P6.13: the coach in chat — distress and pain guards, savage triggers (excuses, food),
max profanity, unknown commands, soft mode — against the fake Telegram API and the stubbed
trainsync API (ADR 0030, 0032)."""

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
from tests.support.chat_links import chat_links
from tests.support.state import MemoryStateStore
from tests.support.swears import swears
from tests.support.telegram import (
    BOT_TOKEN,
    BOT_URL,
    TELEGRAM,
    SleepRecorder,
    message_update,
    ok,
    sent_messages,
)
from trainsync.core.settings import BotLang, BotProfanity
from trainsync.entrypoints.bot.dispatcher import Commands, Dispatcher
from trainsync.integrations.telegram.client import TelegramApi, Update
from trainsync.modules.chat.checkin import CheckinFlow
from trainsync.modules.chat.coach import CoachFeature
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.guardrails import violations
from trainsync.modules.coach.lines import SAVAGE, SAVAGE_MAX, MemoryRecentStore, load_pack
from trainsync.modules.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.modules.coach.packs import PACKS, Key, Messages, NeutralKey
from trainsync.modules.coach.savage_tr import LINES
from trainsync.modules.coach.voice import CoachVoice

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)  # Monday 12:00 in Istanbul
ZONE = ZoneInfo("Europe/Istanbul")
CHAT = 42
TR_HARD = Messages(PACKS["hardcore", "tr"])
HARD: dict[BotLang, Messages] = {"tr": TR_HARD, "en": Messages(PACKS["hardcore", "en"])}


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

    async def __call__(self, chat_id: int, text: str, asker: object) -> str:
        self.questions.append(text)
        return "assistant answer"


@pytest.fixture
def assistant() -> Assistant:
    return Assistant()


def voice(
    soft: MemorySoftModeStore,
    *,
    savage: bool = True,
    seed: int = 5,
    lang: BotLang = "tr",
    profanity: BotProfanity = "roast",
) -> CoachVoice:
    return CoachVoice(
        msg=HARD[lang],
        mode=CoachMode(configured=savage, soft=soft),
        pack=load_pack(None, lang),
        recent=MemoryRecentStore(),
        rng=random.Random(seed),
        profanity=profanity,
    )


def make(
    http: httpx.AsyncClient,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    *,
    savage: bool = True,
    lang: BotLang = "tr",
    profanity: BotProfanity = "roast",
) -> Dispatcher:
    telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM, sleep=SleepRecorder())
    api = ReadApi(http, API, SecretStr("bot-key"))
    clock = lambda: NOW  # noqa: E731
    msg = HARD[lang]
    coach_voice = voice(soft, savage=savage, lang=lang, profanity=profanity)
    store = MemoryStateStore()
    return Dispatcher(
        telegram,
        Commands(api, clock, msg),
        chat_links(http, API, clock),
        msg,
        assistant,
        features=[
            CheckinFlow(api, store, clock, ZONE, msg, coach_voice),
            CoachFeature(api, coach_voice, soft, clock, ZONE, msg, time(18, 0)),
        ],
        voice=coach_voice,
    )


async def say(dispatcher: Dispatcher, router: respx.MockRouter, text: str, update_id: int) -> str:
    await dispatcher.handle(Update.model_validate(message_update(update_id, CHAT, text)))
    return [m["text"] for m in sent_messages(router["send"])][-1]


ROASTS = {
    line
    for pools in (SAVAGE, SAVAGE_MAX)
    for pool in pools.values()
    for lines in pool.values()
    for line in lines
}


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


@pytest.mark.parametrize(
    ("lang", "text"),
    [("tr", "Bu akşam baklava yiyeceğim"), ("en", "Having a big plate of baklava tonight")],
)
async def test_baklava_gets_a_food_roast_a_swap_and_the_unchanged_target(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    lang: BotLang,
    text: str,
) -> None:
    """ADR 0032: the choice is roasted, then one concrete move, then the day's target."""
    msg = HARD[lang]
    reply = await say(make(http, soft, assistant, lang=lang), router, text, 1)
    roast, move, target = reply.split("\n")
    assert any(roast.startswith(line) for line in SAVAGE[lang][Category.FOOD_ROAST]), roast
    assert move == msg.neutral(NeutralKey.FOOD_MOVE_SWEET)
    assert target == msg.neutral(NeutralKey.FOOD_TARGET, target="2600 kcal", remaining="2600 kcal")
    assert violations(reply) == []
    assert assistant.questions == []


@pytest.mark.parametrize(
    ("text", "move"),
    [
        ("akşam pizza yiyeceğim", NeutralKey.FOOD_MOVE_FAST_FOOD),
        ("patates kızartması aldım", NeutralKey.FOOD_MOVE_FRIED),
        ("bu akşam rakı içeceğiz", NeutralKey.FOOD_MOVE_ALCOHOL),
        ("bir sigara yaktım", NeutralKey.FOOD_MOVE_SMOKING),
        ("dün gece sabaha kadar dizi izledim", NeutralKey.FOOD_MOVE_LATE),
    ],
)
async def test_each_kind_of_choice_gets_its_own_move(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    text: str,
    move: NeutralKey,
) -> None:
    fake.kcal_target = None
    reply = await say(make(http, soft, assistant), router, text, 1)
    assert reply.split("\n")[1:] == [
        TR_HARD.neutral(move),
        TR_HARD.neutral(NeutralKey.FOOD_NO_TARGET),
    ]


async def test_without_savage_food_talk_goes_to_the_assistant(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    reply = await say(make(http, soft, assistant, savage=False), router, "baklava yedim", 1)
    assert reply == "assistant answer"


@pytest.mark.parametrize(
    "text",
    [
        "yediğime pişmanım, kendimi suçlu hissediyorum",
        "baklava yedim sonra kustum",
        "bugün hiçbir şey yemedim",
        "kendimden nefret ediyorum",
        "dün gece tıkındım, durduramadım",
        "I feel so guilty about the cake",
        "I threw up after dinner",
        "haven't eaten all day",
        "I hate myself",
        "I binged on pizza last night",
    ],
)
@pytest.mark.parametrize("lang", ["tr", "en"])
async def test_distress_gets_a_calm_reply_without_swearing_even_in_max(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    text: str,
    lang: BotLang,
) -> None:
    """Distress beats food, pain and excuses, in every profanity level (ADR 0032)."""
    dispatcher = make(http, soft, assistant, lang=lang, profanity="max")
    reply = await say(dispatcher, router, text, 1)
    assert reply == HARD[lang].neutral(NeutralKey.SAFETY_DISTRESS)
    assert not swears(reply)
    assert not has_roast(reply)
    assert assistant.questions == []


@pytest.mark.parametrize("text", ["dizim sakatlandı, baklava yedim", "I'm injured", "hastayım"])
async def test_injury_is_clean_even_in_max(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
    text: str,
) -> None:
    reply = await say(make(http, soft, assistant, profanity="max"), router, text, 1)
    assert reply == TR_HARD.neutral(NeutralKey.SAFETY_PAIN)
    assert not swears(reply)


async def test_max_swears_in_a_neutral_reply_and_roasts_from_the_max_pool(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    dispatcher = make(http, soft, assistant, profanity="max")
    soft_off = await say(dispatcher, router, "/sert", 1)
    opener, rest = soft_off.split("\n", 1)
    assert opener in SAVAGE_MAX["tr"][Category.MAX_OPENER]
    assert rest == TR_HARD(Key.COACH_SOFT_OFF)
    # Soft mode is normal intensity: nothing is added, in max too.
    assert await say(dispatcher, router, "/yumusak", 2) == TR_HARD(Key.COACH_SOFT_ON)
    await soft.harden()
    food = await say(dispatcher, router, "baklava yiyeceğim", 3)
    first = food.split("\n")[0]
    assert any(first.startswith(line) for line in SAVAGE_MAX["tr"][Category.FOOD_ROAST]), first
    assert swears(first)


async def test_unknown_commands_point_to_help_in_the_current_tone(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    soft: MemorySoftModeStore,
    assistant: Assistant,
) -> None:
    normal = await say(make(http, soft, assistant, savage=False), router, "/harder", 1)
    assert normal == TR_HARD(Key.UNKNOWN_COMMAND, command="harder", help="")
    assert "/help" in normal
    savage = await say(make(http, soft, assistant), router, "/harder", 2)
    line, pointer = savage.split("\n")
    assert any(line.startswith(roast) for roast in LINES[Category.UNKNOWN_COMMAND]), line
    assert pointer == TR_HARD(Key.HELP_POINTER)
    maxed = await say(make(http, soft, assistant, profanity="max"), router, "/harder", 3)
    assert any(maxed.startswith(roast) for roast in SAVAGE_MAX["tr"][Category.UNKNOWN_COMMAND])
    assert maxed.count("\n") == 1  # no opener on top of a max line


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
