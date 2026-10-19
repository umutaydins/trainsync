"""How often the assistant may be asked: per chat per hour, and per user per local day."""

from dataclasses import dataclass
from typing import Protocol
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from trainsync.core.clock import Clock

SECONDS_PER_HOUR = 3600
# A day key outlives its day in every time zone.
DAILY_KEY_TTL_S = 2 * 24 * SECONDS_PER_HOUR


class RateLimiter(Protocol):
    async def allow(self, chat_id: int) -> bool: ...


class RedisRateLimiter:
    """Fixed one-hour windows per chat: `INCR` a key that expires with its window."""

    def __init__(self, redis: Redis, limit_per_hour: int, clock: Clock) -> None:
        self._redis = redis
        self._limit = limit_per_hour
        self._clock = clock

    async def allow(self, chat_id: int) -> bool:
        window = int(self._clock().timestamp()) // SECONDS_PER_HOUR
        key = f"assistant:quota:{chat_id}:{window}"
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, SECONDS_PER_HOUR)
        return count <= self._limit


@dataclass(frozen=True, slots=True)
class Asker:
    """Who asks: the daily limit counts per user and local day; the owner is exempt."""

    user_id: int
    timezone: str
    unlimited: bool = False


class DailyQuota:
    """`ASSISTANT_DAILY_LIMIT` questions per user per local day (the owner pays for the key)."""

    def __init__(self, redis: Redis, limit: int, clock: Clock) -> None:
        self._redis = redis
        self._limit = limit
        self._clock = clock

    async def allow(self, asker: Asker) -> bool:
        if asker.unlimited:
            return True
        day = self._clock().astimezone(ZoneInfo(asker.timezone)).date()
        key = f"assistant:daily:{asker.user_id}:{day:%Y%m%d}"
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, DAILY_KEY_TTL_S)
        return count <= self._limit
