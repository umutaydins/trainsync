"""Effective intensity (ADR 0030): savage only when configured (hardcore and savage, in either
language since ADR 0031) and not in the owner's 24-hour soft mode (`/yumusak`). Soft mode is a
Redis key that the bot sets and the worker reads."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from redis.asyncio import Redis

from trainsync.core.settings import Settings

SOFT_KEY = "coach:soft"
SOFT_FOR = timedelta(hours=24)


class SoftModeStore(Protocol):
    async def is_soft(self) -> bool: ...

    async def soften(self) -> None: ...

    async def harden(self) -> None: ...


class RedisSoftModeStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def is_soft(self) -> bool:
        return bool(await self._redis.exists(SOFT_KEY))

    async def soften(self) -> None:
        await self._redis.set(SOFT_KEY, "1", ex=int(SOFT_FOR.total_seconds()))

    async def harden(self) -> None:
        await self._redis.delete(SOFT_KEY)


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
        return self.configured and not await self.soft.is_soft()
