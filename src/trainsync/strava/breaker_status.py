"""Shares each process's circuit-breaker state through Redis, for `GET /v1/sync/status`.

Breakers are per process (ADR 0005), so the API process cannot see a worker's breaker. Every
process writes its state on each transition to `breaker:{process}`. The key expires so a dead
process does not linger: an open state shortly after its probe time, other states after a day.
"""

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta

from redis.asyncio import Redis

from trainsync.core.clock import Clock, utc_now
from trainsync.strava.breaker import BreakerState

KEY_PREFIX = "breaker:"
OPEN_GRACE = timedelta(minutes=10)
IDLE_TTL = timedelta(days=1)
_SEVERITY = {BreakerState.CLOSED: 0, BreakerState.HALF_OPEN: 1, BreakerState.OPEN: 2}


def process_name(role: str) -> str:
    return f"{role}@{socket.gethostname()}:{os.getpid()}"


@dataclass(frozen=True, slots=True)
class BreakerReport:
    process: str
    state: BreakerState
    retry_at: datetime | None
    changed_at: datetime

    def effective_state(self, now: datetime) -> BreakerState:
        """An open breaker past its probe time lets the next call through: half-open."""
        if self.state is BreakerState.OPEN and self.retry_at is not None and self.retry_at <= now:
            return BreakerState.HALF_OPEN
        return self.state


class RedisBreakerPublisher:
    """A `BreakerListener` that writes the state to Redis."""

    def __init__(self, redis: Redis, process: str, clock: Clock = utc_now) -> None:
        self._redis = redis
        self._process = process
        self._clock = clock

    async def __call__(self, state: BreakerState, retry_at: datetime | None) -> None:
        now = self._clock()
        value = json.dumps(
            {
                "state": state.value,
                "retry_at": retry_at.isoformat() if retry_at else None,
                "changed_at": now.isoformat(),
            }
        )
        expires = (retry_at - now + OPEN_GRACE) if retry_at else IDLE_TTL
        ttl = max(60, int(expires.total_seconds()))
        await self._redis.set(f"{KEY_PREFIX}{self._process}", value, ex=ttl)


async def read_breakers(redis: Redis) -> list[BreakerReport]:
    keys = sorted([key async for key in redis.scan_iter(match=f"{KEY_PREFIX}*", count=100)])
    if not keys:
        return []
    reports = []
    for key, raw in zip(keys, await redis.mget(keys), strict=True):
        if raw is None:
            continue  # expired between SCAN and MGET
        data = json.loads(raw)
        name = key.decode() if isinstance(key, bytes) else key
        reports.append(
            BreakerReport(
                process=name.removeprefix(KEY_PREFIX),
                state=BreakerState(data["state"]),
                retry_at=datetime.fromisoformat(data["retry_at"]) if data["retry_at"] else None,
                changed_at=datetime.fromisoformat(data["changed_at"]),
            )
        )
    return reports


def overall_state(reports: list[BreakerReport], now: datetime) -> BreakerState:
    """The worst state across processes; no reports means nothing ever tripped."""
    states = [r.effective_state(now) for r in reports]
    return max(states, key=_SEVERITY.__getitem__, default=BreakerState.CLOSED)
