"""`/swear` (P6.13, ADR 0032): the user's profanity level, chosen at runtime from the chat.

`/swear` shows two buttons, `/swear max` and `/swear roast` switch directly. The choice is a
setting of the linked user (ADR 0036), so it survives restarts; without one, `BOT_PROFANITY`
applies. It only changes anything while the savage coach is on. The
confirmation is in the current tone, at the new level (a savage `profanity_set` line in savage).
"""

from trainsync.core.logging import get_logger
from trainsync.core.settings import BotProfanity
from trainsync.integrations.telegram.client import Button, Keyboard
from trainsync.modules.chat.common import Incoming, Press, PressResult, Reply
from trainsync.modules.chat.links import ChatLinks
from trainsync.modules.coach.categories import Category
from trainsync.modules.coach.mode import using_profanity
from trainsync.modules.coach.packs import Key, Messages
from trainsync.modules.coach.voice import CoachVoice

log = get_logger(__name__)

PREFIX = "swear:"
LEVELS: tuple[BotProfanity, ...] = ("max", "roast")
CONFIRM: dict[BotProfanity, Key] = {"max": Key.SWEAR_SET_MAX, "roast": Key.SWEAR_SET_ROAST}


def parse_level(value: str) -> BotProfanity | None:
    value = value.strip().lower()
    return next((level for level in LEVELS if level == value), None)


def keyboard() -> Keyboard:
    return (tuple(Button(level, f"{PREFIX}{level}") for level in LEVELS),)


class SwearFeature:
    commands = frozenset({"swear"})

    def __init__(self, store: ChatLinks, msg: Messages, voice: CoachVoice | None) -> None:
        self._store = store
        self._msg = msg
        self._voice = voice

    async def command(self, incoming: Incoming, command: str, args: list[str]) -> Reply:
        if not args:
            return Reply(self._msg(Key.SWEAR_CHOOSE), keyboard())
        level = parse_level(args[0])
        if level is None or len(args) > 1:
            return Reply(self._msg(Key.SWEAR_USAGE))
        return await self._switch(incoming.chat_id, level)

    async def text(self, incoming: Incoming) -> Reply | None:
        return None

    async def press(self, press: Press) -> PressResult | None:
        if not press.data.startswith(PREFIX):
            return None
        level = parse_level(press.data.removeprefix(PREFIX))
        if level is None:
            return PressResult(toast=self._msg(Key.CHECKIN_STALE))
        return PressResult(reply=await self._switch(press.chat_id, level), accepted=True)

    async def _switch(self, chat_id: int, level: BotProfanity) -> Reply:
        await self._store.set(chat_id, profanity=level)
        log.info("bot_profanity_set", chat_id=chat_id, profanity=level)
        with using_profanity(level):
            if self._voice is not None:
                return Reply(await self._voice.line(Category.PROFANITY_SET, CONFIRM[level]))
            return Reply(self._msg(CONFIRM[level]))
