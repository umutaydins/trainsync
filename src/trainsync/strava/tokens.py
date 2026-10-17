"""Access tokens that are always valid: proactive refresh under a per-athlete Redis lock.

API and worker are separate processes (and there may be several workers), so the lock must live
in Redis. Whoever does not get the lock waits for it to be released and then re-reads the
tokens: Strava rotates refresh tokens, and a second refresh with the old one would fail (or, worse,
overwrite the new pair with a stale one).
"""

import uuid
from datetime import timedelta
from typing import Protocol

from redis.asyncio import Redis

from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.logging import get_logger
from trainsync.db.repositories.tokens import Tokens
from trainsync.strava.errors import StravaAuthError, StravaError
from trainsync.strava.models import TokenResponse

log = get_logger(__name__)

REFRESH_MARGIN = timedelta(minutes=5)

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class TokenStore(Protocol):
    async def get(self, athlete_id: int) -> Tokens | None: ...

    async def save(self, athlete_id: int, tokens: Tokens) -> None: ...


class TokenRefresher(Protocol):
    async def refresh(self, refresh_token: str) -> TokenResponse: ...


class RefreshLock(Protocol):
    async def acquire(self, athlete_id: int) -> str | None:
        """Return an owner token if the lock was taken, `None` if someone else holds it."""

    async def release(self, athlete_id: int, owner: str) -> None: ...

    async def is_held(self, athlete_id: int) -> bool: ...


class TokenRefreshTimeoutError(StravaError):
    """Another process held the refresh lock for too long."""


class RedisRefreshLock:
    """`SET token-refresh:{id} <uuid> NX PX ttl`; released by compare-and-delete."""

    def __init__(self, redis: Redis, ttl_ms: int = 15_000) -> None:
        self._redis = redis
        self._ttl_ms = ttl_ms
        self._release = redis.register_script(_RELEASE_SCRIPT)

    @staticmethod
    def key(athlete_id: int) -> str:
        return f"token-refresh:{athlete_id}"

    async def acquire(self, athlete_id: int) -> str | None:
        owner = uuid.uuid4().hex
        acquired = await self._redis.set(self.key(athlete_id), owner, nx=True, px=self._ttl_ms)
        return owner if acquired else None

    async def release(self, athlete_id: int, owner: str) -> None:
        await self._release(keys=[self.key(athlete_id)], args=[owner])

    async def is_held(self, athlete_id: int) -> bool:
        return bool(await self._redis.exists(self.key(athlete_id)))


class TokenManager:
    def __init__(
        self,
        store: TokenStore,
        lock: RefreshLock,
        refresher: TokenRefresher,
        *,
        clock: Clock = utc_now,
        sleep: Sleep = real_sleep,
        poll_interval: float = 0.05,
        max_wait: float = 10.0,
    ) -> None:
        self._store = store
        self._lock = lock
        self._refresher = refresher
        self._clock = clock
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._max_polls = max(1, int(max_wait / poll_interval))

    async def access_token(self, athlete_id: int) -> str:
        tokens = await self._load(athlete_id)
        if not self._expiring(tokens):
            return tokens.access_token
        return await self._refresh(athlete_id, stale_access=None)

    async def force_refresh(self, athlete_id: int) -> str:
        """After a 401: refresh unless someone already replaced the rejected token."""
        tokens = await self._load(athlete_id)
        return await self._refresh(athlete_id, stale_access=tokens.access_token)

    def _expiring(self, tokens: Tokens) -> bool:
        return tokens.expires_at - REFRESH_MARGIN <= self._clock()

    def _needs_refresh(self, tokens: Tokens, stale_access: str | None) -> bool:
        if stale_access is not None:
            return tokens.access_token == stale_access
        return self._expiring(tokens)

    async def _load(self, athlete_id: int) -> Tokens:
        tokens = await self._store.get(athlete_id)
        if tokens is None:
            raise StravaAuthError("athlete has no stored tokens")
        return tokens

    async def _refresh(self, athlete_id: int, stale_access: str | None) -> str:
        while True:
            owner = await self._lock.acquire(athlete_id)
            if owner is not None:
                try:
                    return await self._refresh_locked(athlete_id, stale_access)
                finally:
                    await self._lock.release(athlete_id, owner)
            await self._wait_for_release(athlete_id)
            tokens = await self._load(athlete_id)
            if not self._needs_refresh(tokens, stale_access):
                return tokens.access_token

    async def _refresh_locked(self, athlete_id: int, stale_access: str | None) -> str:
        tokens = await self._load(athlete_id)  # double-check: someone may have just refreshed
        if not self._needs_refresh(tokens, stale_access):
            return tokens.access_token
        response = await self._refresher.refresh(tokens.refresh_token)
        await self._store.save(
            athlete_id,
            Tokens(
                access_token=response.access_token,
                refresh_token=response.refresh_token,
                expires_at=response.expires_at,
                scope=tokens.scope,
            ),
        )
        log.info("token_refreshed", athlete_id=athlete_id, expires_at=response.expires_at)
        return response.access_token

    async def _wait_for_release(self, athlete_id: int) -> None:
        for _ in range(self._max_polls):
            if not await self._lock.is_held(athlete_id):
                return
            await self._sleep(self._poll_interval)
        raise TokenRefreshTimeoutError("token refresh lock was not released in time")
