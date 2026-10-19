"""The chat's stored settings for the worker's messages (P6.12, P6.13; ADR 0031, 0032).

The worker reads `chat_settings` at send time, so a `/lang` or `/swear` switch reaches the next
reminder, check-in, notification or alert without a restart. No row (or a null field): the
default, `BOT_LANG` / `BOT_PROFANITY`.
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Concatenate, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.settings import BotLang
from trainsync.modules.chat.repository import ChatPrefs, ChatSettingsRepository
from trainsync.modules.coach.mode import using_profanity
from trainsync.modules.coach.packs import using_lang


async def stored_prefs(
    sessionmaker: async_sessionmaker[AsyncSession], chat: int | str | None
) -> ChatPrefs:
    if chat is None:
        return ChatPrefs()
    try:
        chat_id = int(chat)
    except ValueError:
        return ChatPrefs()
    async with sessionmaker() as session:
        return await ChatSettingsRepository(session).get(chat_id)


async def stored_lang(
    sessionmaker: async_sessionmaker[AsyncSession], chat: int | str | None
) -> BotLang | None:
    return (await stored_prefs(sessionmaker, chat)).lang


class ChatDeps(Protocol):
    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]: ...

    @property
    def chat_id(self) -> int | None: ...


def in_chat_settings[D: ChatDeps, **P, R](
    job: Callable[Concatenate[D, P], Awaitable[R]],
) -> Callable[Concatenate[D, P], Awaitable[R]]:
    """Run `job(deps, ...)` with the language and profanity level stored for `deps.chat_id`."""

    @wraps(job)
    async def wrapper(deps: D, /, *args: P.args, **kwargs: P.kwargs) -> R:
        prefs = await stored_prefs(deps.sessionmaker, deps.chat_id)
        with using_lang(prefs.lang), using_profanity(prefs.profanity):
            return await job(deps, *args, **kwargs)

    return wrapper
