"""The statistics cache (ADR 0038): long windows in Redis, keyed by the user's data version.

A write to any table the statistics read bumps `user_data_versions.version` (trigger, migration
0018), so the next request builds a new key and the old entry is never read again; it expires
after `STATS_CACHE_TTL_S`. Redis being down only costs speed: the result is computed instead.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.logging import get_logger
from trainsync.core.metrics import STATS_CACHE
from trainsync.core.settings import Settings
from trainsync.modules.stats.models import UserDataVersion

log = get_logger(__name__)
KEY_PREFIX = "stats"


async def data_version(session: AsyncSession, user_id: int) -> int:
    version = await session.scalar(
        select(UserDataVersion.version).where(UserDataVersion.user_id == user_id)
    )
    return version or 0


def cache_key(user_id: int, version: int, view: str, params: dict[str, object]) -> str:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()
    return f"{KEY_PREFIX}:{user_id}:{version}:{view}:{digest[:32]}"


class StatsCache:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl_s = settings.stats_cache_ttl_s
        self._min_days = settings.stats_cache_min_days

    def worth_it(self, window_days: int) -> bool:
        return window_days >= self._min_days

    async def get_or_compute(
        self,
        session: AsyncSession,
        user_id: int,
        view: str,
        params: dict[str, object],
        compute: Callable[[], Awaitable[str]],
    ) -> str:
        """The cached JSON for these parameters, else `compute()` stored for next time."""
        key = cache_key(user_id, await data_version(session, user_id), view, params)
        try:
            cached = await self._redis.get(key)
        except RedisError as exc:
            log.warning("stats_cache_unavailable", error=str(exc))
            STATS_CACHE.labels("error").inc()
            return await compute()
        if cached is not None:
            STATS_CACHE.labels("hit").inc()
            return cached.decode() if isinstance(cached, bytes) else str(cached)
        STATS_CACHE.labels("miss").inc()
        value = await compute()
        try:
            await self._redis.set(key, value, ex=self._ttl_s)
        except RedisError as exc:
            log.warning("stats_cache_unavailable", error=str(exc))
        return value
