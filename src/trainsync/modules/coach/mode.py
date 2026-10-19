"""Effective intensity (ADR 0030): savage only when configured (hardcore and savage, in either
language since ADR 0031) and not in the user's 24-hour soft mode (`/yumusak`). Soft mode is a
Redis key per user that the bot sets and the worker reads.

Intensity and profanity (ADR 0032) are each user's (ADR 0036): `using_intensity()` and
`using_profanity()` set them for the current task (the bot per update, the worker per send),
like the language; without them, `BOT_INTENSITY` / `BOT_PROFANITY` apply. `using_user()` names
the user whose soft mode counts.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from redis.asyncio import Redis

from trainsync.core.settings import BotProfanity, Settings

SOFT_KEY = "coach:soft"
SOFT_FOR = timedelta(hours=24)

CURRENT_PROFANITY: ContextVar[BotProfanity | None] = ContextVar("trainsync_profanity", default=None)
# None = the configured default; set from the user's settings for the current task.
CURRENT_SAVAGE: ContextVar[bool | None] = ContextVar("trainsync_savage", default=None)
CURRENT_USER: ContextVar[int | None] = ContextVar("trainsync_user", default=None)


@contextmanager
def using_profanity(level: BotProfanity | None) -> Iterator[None]:
    """The chat's profanity level inside this block (None: `BOT_PROFANITY`)."""
    token = CURRENT_PROFANITY.set(level)
    try:
        yield
    finally:
        CURRENT_PROFANITY.reset(token)


@contextmanager
def using_intensity(savage: bool | None) -> Iterator[None]:
    """Whether the user's settings make the coach savage (None: the configured default)."""
    token = CURRENT_SAVAGE.set(savage)
    try:
        yield
    finally:
        CURRENT_SAVAGE.reset(token)


@contextmanager
def using_user(user_id: int | None) -> Iterator[None]:
    token = CURRENT_USER.set(user_id)
    try:
        yield
    finally:
        CURRENT_USER.reset(token)


def soft_key() -> str:
    user = CURRENT_USER.get()
    return SOFT_KEY if user is None else f"{SOFT_KEY}:{user}"


class SoftModeStore(Protocol):
    async def is_soft(self) -> bool: ...

    async def soften(self) -> None: ...

    async def harden(self) -> None: ...


class RedisSoftModeStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def is_soft(self) -> bool:
        return bool(await self._redis.exists(soft_key()))

    async def soften(self) -> None:
        await self._redis.set(soft_key(), "1", ex=int(SOFT_FOR.total_seconds()))

    async def harden(self) -> None:
        await self._redis.delete(soft_key())


@dataclass
class MemorySoftModeStore:
    soft: bool = False
    calls: list[str] = field(default_factory=list)

    async def is_soft(self) -> bool:
        return self.soft

    async def soften(self) -> None:
        self.soft = True
        self.calls.append("soften")

    async def harden(self) -> None:
        self.soft = False
        self.calls.append("harden")


def savage_configured(settings: Settings) -> bool:
    """Savage belongs to the hardcore tone; both languages have a savage pack (ADR 0031)."""
    return settings.bot_intensity == "savage" and settings.bot_tone == "hardcore"


@dataclass(frozen=True)
class CoachMode:
    configured: bool
    soft: SoftModeStore

    async def savage(self) -> bool:
        chosen = CURRENT_SAVAGE.get()
        configured = self.configured if chosen is None else chosen
        return configured and not await self.soft.is_soft()
