"""Who a chat belongs to, as the bot sees it (ADR 0036).

The bot asks the API (`GET /v1/telegram/chats/{chat_id}`) and keeps the answer for
`BOT_CHAT_CACHE_S`; `/link`, `/unlink`, `/lang` and `/swear` refresh it at once. An API that
cannot be reached is not cached: the next update asks again.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.settings import BotLang, BotProfanity
from trainsync.modules.chat.read_api import ReadApi, ReadApiError
from trainsync.modules.chat.router import ChatOwner
from trainsync.modules.coach.context import UserContext
from trainsync.modules.coach.mode import using_user
from trainsync.modules.users.schemas import SettingsPatch

log = get_logger(__name__)


def user_context(owner: ChatOwner | None) -> UserContext:
    """The user's context for an update. Only what the user chose overrides the bot's own
    defaults (the same environment as the API's), so there is one source of defaults."""
    if owner is None:
        return UserContext()
    values = owner.settings
    chosen = set(values.custom)

    def pick[T](name: str, value: T) -> T | None:
        return value if name in chosen else None

    savage = values.intensity == "savage" and values.tone == "hardcore"
    return UserContext(
        user_id=owner.user_id,
        tone=pick("tone", values.tone),
        lang=pick("lang", values.lang),
        savage=savage if chosen & {"tone", "intensity"} else None,
        profanity=pick("profanity", values.profanity),
        emergency_number=pick("country", values.emergency_number),
        timezone=values.timezone,
        workout_reminder_time=pick("workout_reminder_time", values.workout_reminder_time),
        sugar_limit_g=pick("sugar_limit_g", values.sugar_limit_g),
    )


@dataclass(frozen=True, slots=True)
class _Entry:
    owner: ChatOwner | None
    until: datetime


class ChatLinks:
    def __init__(self, api: ReadApi, clock: Clock, ttl_s: int) -> None:
        self._api = api
        self._clock = clock
        self._ttl = timedelta(seconds=ttl_s)
        self._cache: dict[int, _Entry] = {}

    def _remember(self, chat_id: int, owner: ChatOwner | None) -> ChatOwner | None:
        self._cache[chat_id] = _Entry(owner, self._clock() + self._ttl)
        return owner

    def forget(self, chat_id: int) -> None:
        self._cache.pop(chat_id, None)

    async def owner(self, chat_id: int) -> ChatOwner | None:
        """The linked user, or None when the chat is not linked. Raises `ReadApiError` when
        the API cannot say (nothing is cached then: the next update asks again)."""
        entry = self._cache.get(chat_id)
        if entry is not None and entry.until > self._clock():
            return entry.owner
        return self._remember(chat_id, await self._api.chat_owner(chat_id))

    async def prefs(self, chat_id: int) -> UserContext:
        try:
            return user_context(await self.owner(chat_id))
        except ReadApiError as exc:
            log.warning("bot_chat_owner_unavailable", chat_id=chat_id, error=str(exc))
            return UserContext()

    async def link(self, chat_id: int, code: str) -> ChatOwner | None:
        """None when the code is invalid, used or expired."""
        owner = await self._api.link_chat(chat_id, code)
        self.forget(chat_id)
        return self._remember(chat_id, owner) if owner is not None else None

    async def unlink(self, chat_id: int) -> None:
        await self._api.unlink_chat(chat_id)
        self._remember(chat_id, None)

    async def set(
        self,
        chat_id: int,
        lang: BotLang | None = None,
        *,
        profanity: BotProfanity | None = None,
    ) -> None:
        """Store `/lang` or `/swear` in the linked user's settings."""
        owner = await self.owner(chat_id)
        if owner is None:
            return
        chosen = {"lang": lang, "profanity": profanity}
        patch = SettingsPatch.model_validate({k: v for k, v in chosen.items() if v is not None})
        with using_user(owner.user_id):
            stored = await self._api.patch_settings(patch)
        self._remember(chat_id, owner.model_copy(update={"settings": stored}))
