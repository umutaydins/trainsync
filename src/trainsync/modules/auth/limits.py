"""Login and registration limits (ADR 0034): fixed windows counted in Redis.

- Per email: after `LOGIN_MAX_FAILURES` failures in a `LOGIN_LOCKOUT_MINUTES` window the email is
  locked until the window ends, even for the right password.
- Per client address: `LOGIN_MAX_FAILURES_PER_IP` failures per window, `REGISTER_MAX_PER_HOUR`
  registrations per hour. Behind the web BFF the address is the BFF's; the BFF keeps its own
  per-browser limiter in front.

Emails are hashed into the key, so Redis never holds an address book.
"""

import hashlib
from dataclasses import dataclass

from redis.asyncio import Redis

from trainsync.core.clock import Clock
from trainsync.core.settings import Settings

HOUR_S = 3600
KEY_PREFIX = "auth:limit"


@dataclass(frozen=True, slots=True)
class Window:
    """A fixed window of `seconds`; `index` names it, `left` is the seconds until it ends."""

    index: int
    left: int


class AuthLimiter:
    def __init__(self, redis: Redis, clock: Clock, settings: Settings) -> None:
        self._redis = redis
        self._clock = clock
        self._lockout_s = settings.login_lockout_minutes * 60
        self._max_email = settings.login_max_failures
        self._max_ip = settings.login_max_failures_per_ip
        self._max_register = settings.register_max_per_hour

    def _window(self, seconds: int) -> Window:
        now = int(self._clock().timestamp())
        return Window(now // seconds, seconds - now % seconds)

    async def _count(self, key: str) -> int:
        value = await self._redis.get(key)
        return int(value) if value is not None else 0

    async def _bump(self, key: str, ttl_s: int) -> int:
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, ttl_s)
        return count

    def _email_key(self, email: str, window: Window) -> str:
        digest = hashlib.sha256(email.encode()).hexdigest()[:32]
        return f"{KEY_PREFIX}:email:{digest}:{window.index}"

    def _ip_key(self, kind: str, address: str, window: Window) -> str:
        return f"{KEY_PREFIX}:{kind}:{address}:{window.index}"

    async def login_blocked(self, email: str, address: str) -> int | None:
        """Seconds until a login may be tried again, or None."""
        window = self._window(self._lockout_s)
        if await self._count(self._email_key(email, window)) >= self._max_email:
            return window.left
        if await self._count(self._ip_key("login", address, window)) >= self._max_ip:
            return window.left
        return None

    async def login_failed(self, email: str, address: str) -> None:
        window = self._window(self._lockout_s)
        await self._bump(self._email_key(email, window), self._lockout_s)
        await self._bump(self._ip_key("login", address, window), self._lockout_s)

    async def login_succeeded(self, email: str) -> None:
        await self._redis.delete(self._email_key(email, self._window(self._lockout_s)))

    async def register_blocked(self, address: str) -> int | None:
        window = self._window(HOUR_S)
        count = await self._count(self._ip_key("register", address, window))
        return window.left if count >= self._max_register else None

    async def registered(self, address: str) -> None:
        await self._bump(self._ip_key("register", address, self._window(HOUR_S)), HOUR_S)
