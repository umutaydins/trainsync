"""`/lang` (P6.12, ADR 0031): the user's language, chosen at runtime from the chat.

The choice is stored in the linked user's settings through the API (ADR 0036), so it survives
restarts and reaches the worker; no choice means `BOT_LANG`. The dispatcher sets the user's voice
for each update; every reply, the coach lines and the assistant follow it. Command names and help
stay English.
"""

from trainsync.core.logging import get_logger
from trainsync.core.settings import BotLang
from trainsync.integrations.telegram.client import Button, Keyboard
from trainsync.modules.chat.common import Incoming, Press, PressResult, Reply
from trainsync.modules.chat.links import ChatLinks
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.packs import LANGUAGES, Key, Messages, using_lang
from trainsync.modules.coach.voice import CoachVoice

log = get_logger(__name__)

PREFIX = "lang:"
LABELS: dict[BotLang, str] = {"tr": "Türkçe", "en": "English"}


def parse_lang(value: str) -> BotLang | None:
    value = value.strip().lower()
    return next((lang for lang in LANGUAGES if lang == value), None)


def keyboard() -> Keyboard:
    return (tuple(Button(LABELS[lang], f"{PREFIX}{lang}") for lang in ("tr", "en")),)


class LanguageFeature:
    """`/lang` shows two buttons; `/lang tr` and `/lang en` switch directly. The confirmation
    is in the new language and the current intensity (a savage line in savage mode)."""

    commands = frozenset({"lang"})

    def __init__(self, store: ChatLinks, msg: Messages, voice: CoachVoice | None) -> None:
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
