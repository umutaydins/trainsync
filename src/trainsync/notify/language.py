"""The chat's stored language for the worker's messages (P6.12, ADR 0031).

The worker reads `chat_settings` at send time, so a `/lang` switch reaches the next reminder,
check-in, notification or alert without a restart. No row: `BOT_LANG`.
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Concatenate, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.bot.messages import using_lang
from trainsync.core.settings import BotLang
from trainsync.db.repositories.chat_settings import ChatSettingsRepository


async def stored_lang(
    sessionmaker: async_sessionmaker[AsyncSession], chat: int | str | None
) -> BotLang | None:
    if chat is None:
        return None
    try:
        chat_id = int(chat)
    except ValueError:
        return None
    async with sessionmaker() as session:
        return await ChatSettingsRepository(session).lang(chat_id)


class ChatDeps(Protocol):
    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]: ...

    @property
    def chat_id(self) -> int | None: ...


def in_chat_lang[D: ChatDeps, **P, R](
    job: Callable[Concatenate[D, P], Awaitable[R]],
) -> Callable[Concatenate[D, P], Awaitable[R]]:
    """Run `job(deps, ...)` with the language stored for `deps.chat_id`."""

    @wraps(job)
    async def wrapper(deps: D, /, *args: P.args, **kwargs: P.kwargs) -> R:
        with using_lang(await stored_lang(deps.sessionmaker, deps.chat_id)):
            return await job(deps, *args, **kwargs)

    return wrapper
