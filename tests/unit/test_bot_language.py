"""P6.12: `/lang` — buttons and arguments, the stored language per chat, the default `BOT_LANG`,
every reply in the chat's language, help in English, confirmations in the current intensity
(ADR 0031). The API (chat settings) and Telegram are respx stubs."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.

import random
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import make_settings
from tests.support.chat_settings import ChatSettingsApi
from tests.support.telegram import BOT_TOKEN, BOT_URL, TELEGRAM, message_update, ok, sent_messages
from trainsync.core.settings import BotLang
from trainsync.entrypoints.bot.dispatcher import Commands, Dispatcher
from trainsync.integrations.telegram.client import TelegramApi, Update
from trainsync.modules.chat.language import ChatSettingsStore, LanguageFeature
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.lines import MemoryRecentStore, load_packs
from trainsync.modules.coach.mode import CoachMode, MemorySoftModeStore
from trainsync.modules.coach.packs import LANGUAGES, PACKS, Key, Messages, messages_for, using_lang
from trainsync.modules.coach.voice import CoachVoice

API = "http://trainsync-api"
CHAT = 42


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
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


class Bot:
    def __init__(self, http: httpx.AsyncClient, router: respx.MockRouter, **settings: Any) -> None:
        self.router = router
        self.msg = messages_for(make_settings(**settings), random.Random(1))
        intensity = settings.get("bot_intensity") == "savage"
        self.voice = CoachVoice(
            msg=self.msg,
            mode=CoachMode(configured=intensity, soft=MemorySoftModeStore()),
            pack=load_packs(None)[self.msg.lang],
            recent=MemoryRecentStore(),
            rng=random.Random(2),
            packs=load_packs(None),
        )
        api = ReadApi(http, API, SecretStr("bot-key"))
        self.store = ChatSettingsStore(api)
        telegram = TelegramApi(http, SecretStr(BOT_TOKEN), base_url=TELEGRAM)
        self.dispatcher = Dispatcher(
            telegram,
            Commands(api, lambda: None, self.msg),  # type: ignore[arg-type, return-value]
            {CHAT},
            self.msg,
            features=[LanguageFeature(self.store, self.msg, self.voice)],
            chat_settings=self.store,
        )
        self._update = 0

    def _next(self) -> int:
        self._update += 1
        return self._update

    async def say(self, text: str) -> dict[str, Any]:
        update = message_update(self._next(), CHAT, text)
        await self.dispatcher.handle(Update.model_validate(update))
        return self.sent[-1]

    async def press(self, data: str) -> dict[str, Any]:
        update = {
            "update_id": self._next(),
            "callback_query": {
                "id": "cq",
                "data": data,
                "message": {"message_id": 7, "chat": {"id": CHAT}},
            },
        }
        await self.dispatcher.handle(Update.model_validate(update))
        return self.sent[-1]

    @property
    def sent(self) -> list[dict[str, Any]]:
        return sent_messages(self.router["send"])


def neutral(lang: BotLang) -> Messages:
    return Messages(PACKS["neutral", lang])


async def test_lang_shows_two_buttons(http: httpx.AsyncClient, router: respx.MockRouter) -> None:
    bot = Bot(http, router)
    sent = await bot.say("/lang")
    assert sent["text"] == neutral("en")(Key.LANG_CHOOSE)
    buttons = sent["reply_markup"]["inline_keyboard"][0]
    assert [(b["text"], b["callback_data"]) for b in buttons] == [
        ("Türkçe", "lang:tr"),
        ("English", "lang:en"),
    ]


async def test_a_button_switches_and_confirms_in_the_new_language(
    http: httpx.AsyncClient, router: respx.MockRouter, db: ChatSettingsApi
) -> None:
    bot = Bot(http, router)
    assert (await bot.press("lang:tr"))["text"] == neutral("tr")(Key.LANG_SET)
    assert db.lang(CHAT) == "tr"
    # Every later reply is Turkish: an unknown command, for example.
    reply = await bot.say("/nope")
    assert reply["text"].startswith("Bilinmeyen komut: /nope.")


async def test_lang_with_an_argument_and_a_bad_argument(
    http: httpx.AsyncClient, router: respx.MockRouter, db: ChatSettingsApi
) -> None:
    bot = Bot(http, router, bot_lang="tr")
    assert (await bot.say("/lang en"))["text"] == neutral("en")(Key.LANG_SET)
    assert (await bot.say("/lang TR"))["text"] == neutral("tr")(Key.LANG_SET)
    assert (await bot.say("/lang de"))["text"] == neutral("tr")(Key.LANG_USAGE)
    assert db.lang(CHAT) == "tr"


async def test_without_a_stored_choice_the_bot_speaks_bot_lang(
    http: httpx.AsyncClient, router: respx.MockRouter
) -> None:
    bot = Bot(http, router, bot_lang="tr")
    assert (await bot.say("/nope"))["text"].startswith("Bilinmeyen komut")
    bot = Bot(http, router, bot_lang="en")
    assert (await bot.say("/nope"))["text"].startswith("Unknown command")


async def test_the_choice_survives_a_restart(
    http: httpx.AsyncClient, router: respx.MockRouter, db: ChatSettingsApi
) -> None:
    await Bot(http, router, bot_lang="en").say("/lang tr")
    restarted = Bot(http, router, bot_lang="en")  # a new process: empty cache, same database
    assert (await restarted.say("/nope"))["text"].startswith("Bilinmeyen komut")
    reads = db.reads
    await restarted.say("/nope")
    assert db.reads == reads  # cached after the first read


async def test_an_unreachable_api_falls_back_to_bot_lang_and_asks_again(
    http: httpx.AsyncClient, router: respx.MockRouter, db: ChatSettingsApi
) -> None:
    db.rows[CHAT] = {"lang": "tr"}
    db.down = True
    bot = Bot(http, router, bot_lang="en")
    assert (await bot.say("/nope"))["text"].startswith("Unknown command")
    db.down = False
    assert (await bot.say("/nope"))["text"].startswith("Bilinmeyen komut")


async def test_help_stays_english_in_both_languages(
    http: httpx.AsyncClient, router: respx.MockRouter
) -> None:
    bot = Bot(http, router, bot_lang="tr")
    english = (await bot.say("/help"))["text"]
    assert english == Messages(PACKS["neutral", "en"]).help()
    assert "/lang" in english


async def test_the_confirmation_follows_the_intensity(
    http: httpx.AsyncClient, router: respx.MockRouter
) -> None:
    hardcore = Bot(http, router, bot_tone="hardcore")
    assert (await hardcore.say("/lang tr"))["text"] == PACKS["hardcore", "tr"].texts[Key.LANG_SET][
        0
    ]
    savage = Bot(http, router, bot_tone="hardcore", bot_intensity="savage")
    savage_tr = load_packs(None)["tr"].lines
    savage_en = load_packs(None)["en"].lines
    tr_text = (await savage.say("/lang tr"))["text"]
    assert any(tr_text.startswith(line) for line in savage_tr[Category.LANGUAGE_SET]), tr_text
    en_text = (await savage.say("/lang en"))["text"]
    assert any(en_text.startswith(line) for line in savage_en[Category.LANGUAGE_SET]), en_text


def test_every_tone_has_a_pack_in_every_language() -> None:
    """Fails when a tone is missing a language: every key must exist in both (ADR 0031)."""
    tones = {tone for tone, _ in PACKS}
    assert set(PACKS) == {(tone, lang) for tone in tones for lang in LANGUAGES}
    for pack in PACKS.values():
        assert set(pack.texts) == set(Key)


def test_using_lang_switches_the_pack_and_restores_it() -> None:
    msg = messages_for(make_settings(bot_lang="en"))
    assert msg.lang == "en"
    with using_lang("tr"):
        assert msg.lang == "tr"
        assert msg(Key.LANG_SET) == neutral("tr")(Key.LANG_SET)
        assert msg.help() == neutral("en").help()
    assert msg.lang == "en"
    with using_lang(None):
        assert msg.lang == "en"
