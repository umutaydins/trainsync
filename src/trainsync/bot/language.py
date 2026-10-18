"""`/lang` (P6.12, ADR 0031): the chat's language, chosen at runtime, and the store of every
per-chat setting (also the profanity level of `/swear`, ADR 0032).

The choices are stored through the API (`chat_settings`), so they survive restarts and
redeploys, and are cached in the process. No stored choice, or an API that cannot be reached,
means the default (`BOT_LANG`, `BOT_PROFANITY`). The dispatcher sets both for each update
(`using_lang`, `using_profanity`); every reply, the coach lines and the assistant follow them.
Command names and help stay English.
"""

from trainsync.api.chats import ChatSettingsIn
from trainsync.bot.common import Incoming, Press, PressResult, Reply
from trainsync.bot.messages import LANGUAGES, Key, Messages, using_lang
from trainsync.bot.read_api import ReadApi, ReadApiError
from trainsync.bot.telegram import Button, Keyboard
from trainsync.coach.categories import Category
from trainsync.coach.voice import CoachVoice
from trainsync.core.logging import get_logger
from trainsync.core.settings import BotLang, BotProfanity
from trainsync.db.repositories.chat_settings import ChatPrefs

log = get_logger(__name__)

PREFIX = "lang:"
LABELS: dict[BotLang, str] = {"tr": "Türkçe", "en": "English"}


def parse_lang(value: str) -> BotLang | None:
    value = value.strip().lower()
    return next((lang for lang in LANGUAGES if lang == value), None)


class ChatSettingsStore:
    """The stored settings per chat, read once per process and kept in memory."""

    def __init__(self, api: ReadApi) -> None:
        self._api = api
        self._cache: dict[int, ChatPrefs] = {}

    async def prefs(self, chat_id: int) -> ChatPrefs:
        if chat_id in self._cache:
            return self._cache[chat_id]
        try:
            stored = await self._api.chat_settings(chat_id)
        except ReadApiError as exc:
            # Not cached: the next update asks again.
            log.warning("bot_chat_settings_unavailable", chat_id=chat_id, error=str(exc))
            return ChatPrefs()
        prefs = ChatPrefs(stored.lang, stored.profanity)
        self._cache[chat_id] = prefs
        return prefs

    async def get(self, chat_id: int) -> BotLang | None:
        """The stored language (None: `BOT_LANG`)."""
        return (await self.prefs(chat_id)).lang

    async def set(
        self,
        chat_id: int,
        lang: BotLang | None = None,
        *,
        profanity: BotProfanity | None = None,
    ) -> None:
        stored = await self._api.put_chat_settings(
            chat_id, ChatSettingsIn(lang=lang, profanity=profanity)
        )
        self._cache[chat_id] = ChatPrefs(stored.lang, stored.profanity)


def keyboard() -> Keyboard:
    return (tuple(Button(LABELS[lang], f"{PREFIX}{lang}") for lang in ("tr", "en")),)


class LanguageFeature:
    """`/lang` shows two buttons; `/lang tr` and `/lang en` switch directly. The confirmation
    is in the new language and the current intensity (a savage line in savage mode)."""

    commands = frozenset({"lang"})

    def __init__(self, store: ChatSettingsStore, msg: Messages, voice: CoachVoice | None) -> None:
        self._store = store
        self._msg = msg
        self._voice = voice

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply:
        if not args:
            return Reply(self._msg(Key.LANG_CHOOSE), keyboard())
        lang = parse_lang(args[0])
        if lang is None or len(args) > 1:
            return Reply(self._msg(Key.LANG_USAGE))
        return await self._switch(incoming.chat_id, lang)

    async def text(self, incoming: Incoming) -> Reply | None:
        return None

    async def press(self, press: Press) -> PressResult | None:
        if not press.data.startswith(PREFIX):
            return None
        lang = parse_lang(press.data.removeprefix(PREFIX))
        if lang is None:
            return PressResult(toast=self._msg(Key.CHECKIN_STALE))
        return PressResult(reply=await self._switch(press.chat_id, lang), accepted=True)

    async def _switch(self, chat_id: int, lang: BotLang) -> Reply:
        await self._store.set(chat_id, lang)
        log.info("bot_language_set", chat_id=chat_id, lang=lang)
        with using_lang(lang):
            if self._voice is not None:
                return Reply(await self._voice.line(Category.LANGUAGE_SET, Key.LANG_SET))
            return Reply(self._msg(Key.LANG_SET))
