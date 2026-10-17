"""Rate-limit budget: may a call of a given priority go to Strava now?

Two priorities share Strava's budget. `low` (backfill, incremental sync) stops at 80% of the
15-minute or the daily budget and resumes in the next window; `high` (webhook-driven fetches)
keeps going until the 15-minute window is actually exhausted. After a 429 both wait until the
window resets. The limits are never hard-coded: they come from the latest `X-RateLimit-*`
headers, stored in Redis so the API and every worker share them.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol

from redis.asyncio import Redis

from trainsync.core.clock import Clock, utc_now
from trainsync.core.metrics import STRAVA_RATELIMIT_USAGE
from trainsync.strava.ratelimit import (
    RateLimitSnapshot,
    next_daily_reset,
    next_window_reset,
    window_start,
)

# `high`: webhook-driven fetches (fresh data the athlete just produced). `low`: backfill and
# incremental sync, which can always wait for the next window.
Priority = Literal["high", "low"]

LATEST_KEY = "ratelimit:latest"
BLOCKED_KEY = "ratelimit:blocked_until"
DEFAULT_LOW_PRIORITY_THRESHOLD = 0.8
_EXHAUSTED = 1.0


@dataclass(frozen=True, slots=True)
class Allowance:
    allowed: bool
    resume_at: datetime | None = None


class Budget(Protocol):
    async def allow(self, priority: Priority) -> Allowance: ...


class UnlimitedBudget:
    async def allow(self, priority: Priority) -> Allowance:
        return Allowance(allowed=True)


@dataclass(frozen=True, slots=True)
class BudgetState:
    """The latest recorded usage, plus the window it was observed in."""

    short_ratio: float
    daily_ratio: float
    window_start: datetime
    blocked_until: datetime | None = None

    def current_short_ratio(self, now: datetime) -> float:
        """Usage resets on the quarter hour: a snapshot from an earlier window says nothing."""
        return self.short_ratio if self.window_start == window_start(now) else 0.0

    def current_daily_ratio(self, now: datetime) -> float:
        return self.daily_ratio if self.window_start.date() == now.date() else 0.0


def decide(
    state: BudgetState | None,
    blocked_until: datetime | None,
    priority: Priority,
    now: datetime,
    low_priority_threshold: float = DEFAULT_LOW_PRIORITY_THRESHOLD,
) -> Allowance:
    """Pure budget decision (docs/diagrams.md §14)."""
    if blocked_until is not None and blocked_until > now:
        return Allowance(False, blocked_until)
    if state is None:
        return Allowance(True)
    threshold = _EXHAUSTED if priority == "high" else low_priority_threshold
    resume: list[datetime] = []
    if state.current_short_ratio(now) >= threshold:
        resume.append(next_window_reset(now))
    if state.current_daily_ratio(now) >= threshold:
        resume.append(next_daily_reset(now))
    if resume:
        return Allowance(False, max(resume))
    return Allowance(True)


class RateBudget:
    def __init__(
        self,
        redis: Redis,
        clock: Clock = utc_now,
        low_priority_threshold: float = DEFAULT_LOW_PRIORITY_THRESHOLD,
    ) -> None:
        self._redis = redis
        self._clock = clock
        self._threshold = low_priority_threshold

    async def record(self, snapshot: RateLimitSnapshot) -> None:
        """Store the usage from the latest response (the StravaClient calls this every time)."""
        now = self._clock()
        overall = snapshot.overall
        STRAVA_RATELIMIT_USAGE.labels("short").set(snapshot.short_ratio)
        STRAVA_RATELIMIT_USAGE.labels("daily").set(snapshot.daily_ratio)
        mapping: dict[str, str] = {
            "short_usage": str(overall.short_usage),
            "short_limit": str(overall.short_limit),
            "daily_usage": str(overall.daily_usage),
            "daily_limit": str(overall.daily_limit),
            "short_ratio": repr(snapshot.short_ratio),
            "daily_ratio": repr(snapshot.daily_ratio),
            "window_start": window_start(now).isoformat(),
            "observed_at": now.isoformat(),
        }
        ttl = _ttl_seconds(next_daily_reset(now) - now)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(LATEST_KEY, mapping=mapping)
            pipe.expire(LATEST_KEY, ttl)
            await pipe.execute()

    async def block_until(self, reset_at: datetime) -> None:
        """After a 429: deny both priorities until `reset_at`."""
        ttl = _ttl_seconds(reset_at - self._clock())
        await self._redis.set(BLOCKED_KEY, reset_at.isoformat(), ex=ttl)

    async def allow(self, priority: Priority) -> Allowance:
        state, blocked = await self._load()
        return decide(state, blocked, priority, self._clock(), self._threshold)

    async def latest(self) -> BudgetState | None:
        """Current usage for status pages; ratios from an earlier window read as 0."""
        state, blocked = await self._load()
        now = self._clock()
        if state is None:
            if blocked is None or blocked <= now:
                return None
            return BudgetState(0.0, 0.0, window_start(now), blocked)
        return BudgetState(
            short_ratio=state.current_short_ratio(now),
            daily_ratio=state.current_daily_ratio(now),
            window_start=state.window_start,
            blocked_until=blocked if blocked is not None and blocked > now else None,
        )

    async def _load(self) -> tuple[BudgetState | None, datetime | None]:
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.hgetall(LATEST_KEY)
            pipe.get(BLOCKED_KEY)
            raw, blocked_raw = await pipe.execute()
        blocked = datetime.fromisoformat(_text(blocked_raw)) if blocked_raw else None
        if not raw:
            return None, blocked
        fields = {_text(k): _text(v) for k, v in raw.items()}
        state = BudgetState(
            short_ratio=float(fields["short_ratio"]),
            daily_ratio=float(fields["daily_ratio"]),
            window_start=datetime.fromisoformat(fields["window_start"]),
        )
        return state, blocked


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _ttl_seconds(delta: timedelta) -> int:
    # Only for cleanup: decisions compare stored timestamps with the injected clock.
    return max(60, int(delta.total_seconds()) + 60)
