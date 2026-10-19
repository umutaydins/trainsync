"""P6.13: `/swear` and the profanity level (ADR 0032) — buttons and arguments, the stored level
per chat (across a restart), the default `BOT_PROFANITY`, max swearing in confirmations, roast
mode keeping them clean, and the savage `/eat` roast of high-sugar and ultra-processed logs. The
API (chat settings, nutrition) and Telegram are respx stubs."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.

import random
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import make_settings
from tests.support.bot_api import API, FakeApi, install
from tests.support.chat_settings import ChatSettingsApi
from tests.support.state import MemoryStateStore
from tests.support.swears import swears
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, message_update, ok, sent_messages
from trainsync.bot.handlers import Commands, Dispatcher
from trainsync.bot.language import ChatSettingsStore, LanguageFeature
from trainsync.bot.messages import Key, Messages, NeutralKey, messages_for
from trainsync.bot.nutrition import NutritionCommands
from trainsync.bot.profanity import SwearFeature
from trainsync.bot.read_api import ReadApi
from trainsync.bot.telegram import TelegramApi, Update
from trainsync.coach.categories import Category
from trainsync.coach.lines import SAVAGE, SAVAGE_MAX, MemoryRecentStore, load_packs
from trainsync.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.coach.voice import CoachVoice

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)  # 12:00 in Istanbul: lunch
ZONE = ZoneInfo("Europe/Istanbul")
CHAT = 42
OPENERS = set(SAVAGE_MAX["tr"][Category.MAX_OPENER])


@pytest.fixture
def db() -> ChatSettingsApi:
    return ChatSettingsApi()


@pytest.fixture
def router(db: ChatSettingsApi) -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        db.install(router, API)
        router.post(f"{BOT_URL}/sendMessage", name="send").mock(return_value=ok({}))
        router.post(f"{BOT_URL}/answerCallbackQuery").mock(return_value=ok(True))
        router.post(f"{BOT_URL}/editMessageReplyMarkup").mock(return_value=ok({}))
        yield router


@pytest.fixture
def fake(router: respx.MockRouter) -> FakeApi:
    return install(router, lambda: NOW)


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


class Bot:
    """One bot process: its own caches, the shared (stubbed) API and database."""

    def __init__(self, http: httpx.AsyncClient, router: respx.MockRouter, **settings: Any) -> None:
        values: dict[str, Any] = {
            "bot_tone": "hardcore",
            "bot_lang": "tr",
            "bot_intensity": "savage",
            **settings,
        }
        config = make_settings(**values)
        self.router = router
        self.msg = messages_for(config, random.Random(1))
        self.soft = MemorySoftModeStore()
        packs = load_packs(None)
        self.voice = CoachVoice(
            msg=self.msg,
            mode=CoachMode(configured=config.bot_intensity == "savage", soft=self.soft),
            pack=packs["tr"],
            recent=MemoryRecentStore(),
            rng=random.Random(2),
            packs=packs,
            profanity=config.bot_profanity,
        )
        api = ReadApi(http, API, SecretStr("bot-key"))
        store = ChatSettingsStore(api)
        clock = lambda: NOW  # noqa: E731
        nutrition = NutritionCommands(
            api, MemoryStateStore(), clock, ZONE, self.msg, voice=self.voice, sugar_limit_g=50
        )
        self.dispatcher = Dispatcher(
            TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM),
            Commands(api, clock, self.msg),
            {CHAT},
            self.msg,
            features=[
                LanguageFeature(store, self.msg, self.voice),
                SwearFeature(store, self.msg, self.voice),
                nutrition,
            ],
            chat_settings=store,
            voice=self.voice,
        )
        self._update = 0

    def _next(self) -> int:
        self._update += 1
        return self._update

    async def say(self, text: str) -> str:
        update = message_update(self._next(), CHAT, text)
        await self.dispatcher.handle(Update.model_validate(update))
        return self.sent[-1]["text"]

    async def press(self, data: str) -> str:
        update = {
            "update_id": self._next(),
            "callback_query": {
                "id": "cq",
                "data": data,
                "message": {"message_id": 7, "chat": {"id": CHAT}},
            },
        }
        await self.dispatcher.handle(Update.model_validate(update))
        return self.sent[-1]["text"]

    @property
    def sent(self) -> list[dict[str, Any]]:
        return sent_messages(self.router["send"])


def saved(msg: Messages, grams: str, food: str, kcal: str) -> str:
    meal = msg.neutral(NeutralKey.MEAL_LUNCH)
    return msg.neutral(NeutralKey.EAT_SAVED, grams=grams, food=food, meal=meal, kcal=kcal)


def split_opener(text: str) -> tuple[str | None, str]:
    first, _, rest = text.partition("\n")
    return (first, rest) if first in OPENERS else (None, text)


async def test_swear_shows_two_buttons(http: httpx.AsyncClient, router: respx.MockRouter) -> None:
    bot = Bot(http, router)
    await bot.say("/swear")
    sent = bot.sent[-1]
    assert sent["text"] == bot.msg(Key.SWEAR_CHOOSE)
    buttons = sent["reply_markup"]["inline_keyboard"][0]
    assert [(b["text"], b["callback_data"]) for b in buttons] == [
        ("max", "swear:max"),
        ("roast", "swear:roast"),
    ]


async def test_a_button_switches_and_confirms_at_the_new_level(
    http: httpx.AsyncClient, router: respx.MockRouter, db: ChatSettingsApi
) -> None:
    bot = Bot(http, router)
    to_max = await bot.press("swear:max")
    assert db.profanity(CHAT) == "max"
    assert any(to_max.startswith(line) for line in SAVAGE_MAX["tr"][Category.PROFANITY_SET])
    assert to_max.count("\n") == 0  # already a max line: no opener on top
    to_roast = await bot.say("/swear roast")
    assert db.profanity(CHAT) == "roast"
    assert any(to_roast.startswith(line) for line in SAVAGE["tr"][Category.PROFANITY_SET])
    assert await bot.say("/swear loud") == bot.msg(Key.SWEAR_USAGE)


async def test_max_applies_to_confirmations_and_roast_keeps_them_clean(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    bot = Bot(http, router)
    clean = await bot.say("/eat oats 60")
    assert clean == saved(bot.msg, "60 g", "Rolled oats", "223 kcal")
    assert not swears(clean)
    await bot.say("/swear max")
    eat = await bot.say("/eat oats 50")
    opener, rest = split_opener(eat)
    assert opener is not None, eat
    assert rest == saved(bot.msg, "50 g", "Rolled oats", "186 kcal")
    weight = await bot.say("/weight 80.4")
    opener, rest = split_opener(weight)
    assert opener is not None, weight
    day = bot.msg.day(date(2026, 10, 18))
    assert rest == bot.msg.neutral(NeutralKey.SCALE_SAVED, day=day, value="80.4 kg")
    lang = await bot.say("/lang tr")  # a savage line from the max pool, no opener
    assert any(lang.startswith(line) for line in SAVAGE_MAX["tr"][Category.LANGUAGE_SET]), lang
    await bot.say("/swear roast")
    again = await bot.say("/eat oats 40")
    assert again == saved(bot.msg, "40 g", "Rolled oats", "149 kcal")
    assert not swears(again)


async def test_the_level_survives_a_restart_and_defaults_to_bot_profanity(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi, db: ChatSettingsApi
) -> None:
    await Bot(http, router).say("/swear max")
    restarted = Bot(http, router)  # a new process: empty cache, same database
    assert split_opener(await restarted.say("/eat oats 50"))[0] is not None
    db.rows.clear()
    default_max = Bot(http, router, bot_profanity="max")
    assert split_opener(await default_max.say("/eat oats 50"))[0] is not None
    default_roast = Bot(http, router)
    assert split_opener(await default_roast.say("/eat oats 50"))[0] is None


async def test_max_needs_savage(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    normal = Bot(http, router, bot_intensity="normal", bot_profanity="max")
    reply = await normal.say("/eat oats 50")
    assert split_opener(reply)[0] is None
    assert not swears(reply)
    soft = Bot(http, router, bot_profanity="max")
    await soft.soft.soften()
    assert not swears(await soft.say("/eat oats 50"))


@pytest.mark.parametrize(
    ("command", "label", "kcal"),
    [
        ("/eat baklava 120", "Baklava", 516),  # 30 g sugar per 100 g
        ("/eat energy bar 50", "Energy bar (Acme)", 200),  # NOVA 4, 15 g sugar per 100 g
    ],
)
async def test_a_high_sugar_or_ultra_processed_log_gets_a_roast(
    http: httpx.AsyncClient,
    router: respx.MockRouter,
    fake: FakeApi,
    command: str,
    label: str,
    kcal: int,
) -> None:
    bot = Bot(http, router)
    reply = await bot.say(command)
    grams = command.rsplit(" ", 1)[1]
    first, roast, move, target = reply.split("\n")
    assert first == saved(bot.msg, f"{grams} g", label, f"{kcal} kcal")
    assert any(roast.startswith(line) for line in SAVAGE["tr"][Category.FOOD_ROAST]), reply
    assert move == bot.msg.neutral(NeutralKey.FOOD_MOVE_LOGGED)
    remaining = f"{2600 - kcal} kcal"
    assert target == bot.msg.neutral(
        NeutralKey.FOOD_TARGET, target="2600 kcal", remaining=remaining
    )


async def test_a_plain_log_is_not_roasted_and_a_day_over_the_sugar_limit_is(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    bot = Bot(http, router)
    assert "\n" not in await bot.say("/eat oats 60")
    await bot.say("/eat baklava 100")  # 30 g sugar
    over = await bot.say("/eat baklava 80")  # +24 g: 54 g, over 50
    assert bot.msg.neutral(NeutralKey.FOOD_SUGAR_DAY, sugar="54 g", limit="50 g") in over
    normal = Bot(http, router, bot_intensity="normal")
    assert "\n" not in await normal.say("/eat baklava 100")  # savage only


@pytest.mark.parametrize(
    "command",
    [
        "/eat apple 600",  # 62 g of fruit sugar
        "/eat plain yogurt 1200",  # 56 g of milk sugar, NOVA 4 in the data
    ],
)
async def test_fruit_and_plain_dairy_never_trigger_a_sugar_roast(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi, command: str
) -> None:
    bot = Bot(http, router)
    reply = await bot.say(command)
    assert "\n" not in reply, reply
    assert "\n" not in await bot.say(command)  # the day's total sugar is past 100 g now


async def test_cola_and_baklava_trigger_and_only_free_sugar_counts_toward_the_limit(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    bot = Bot(http, router)
    assert "\n" not in await bot.say("/eat apple 600")  # 62 g sugar, none of it free
    baklava = await bot.say("/eat baklava 100")  # 30 g free sugar: a roast, under the limit
    assert len(baklava.split("\n")) == 4, baklava
    assert "50 g" not in baklava
    cola = await bot.say("/eat cola 330")  # +35 g: 65 g free sugar
    assert bot.msg.neutral(NeutralKey.FOOD_SUGAR_DAY, sugar="65 g", limit="50 g") in cola


async def test_help_lists_swear(http: httpx.AsyncClient, router: respx.MockRouter) -> None:
    help_text = await Bot(http, router).say("/help")
    assert "/swear: max / roast" in help_text


async def test_a_language_switch_in_max_gets_no_opener_in_the_old_language(
    http: httpx.AsyncClient, router: respx.MockRouter, fake: FakeApi
) -> None:
    bot = Bot(http, router)
    await bot.say("/swear max")
    english = await bot.say("/lang en")
    assert "\n" not in english, english
    assert any(english.startswith(line) for line in SAVAGE_MAX["en"][Category.LANGUAGE_SET])
    eat = await bot.say("/eat oats 50")  # now English, with an English opener
    assert eat.split("\n", 1)[0] in SAVAGE_MAX["en"][Category.MAX_OPENER], eat
