"""Per-process circuit breaker for Strava calls (docs/diagrams.md §11, ADR 0005).

`closed` → `open` after `failure_threshold` consecutive failures; `open` → `half_open` once the
cooldown has passed; in `half_open` exactly one probe goes through, and its outcome closes or
reopens the circuit. Only `StravaUnavailable` (5xx / timeouts / network errors after retries are
exhausted) is a failure. Any other answer from Strava, including 4xx and 429, proves Strava is up
and counts as a success. Errors that say nothing about Strava (a cancelled task, a database error
while loading a token) leave the state alone.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import StrEnum

from trainsync.core.clock import Clock, utc_now
from trainsync.core.logging import get_logger
from trainsync.core.metrics import STRAVA_CIRCUIT_STATE
from trainsync.strava.errors import CircuitOpen, StravaError, StravaUnavailable

log = get_logger(__name__)

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_COOLDOWN = timedelta(seconds=30)


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_GAUGE_VALUE = {"closed": 0, "half_open": 1, "open": 2}

# Called after every state change with the new state and, when open, the time a probe is allowed.
BreakerListener = Callable[[BreakerState, datetime | None], Awaitable[None]]


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown: timedelta = DEFAULT_COOLDOWN,
        clock: Clock = utc_now,
        listener: BreakerListener | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._clock = clock
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at: datetime | None = None
        self._probe = asyncio.Lock()
        self._listener = listener
        self._changed = False

    @property
    def state(self) -> BreakerState:
        """`open` reads as `half_open` once the cooldown has passed (the next call probes)."""
        if self._state is BreakerState.OPEN and self._clock() >= self._retry_at():
            return BreakerState.HALF_OPEN
        return self._state

    @asynccontextmanager
    async def guard(self) -> AsyncIterator[None]:
        """Wrap one logical Strava call; raises `CircuitOpen` without running it if not allowed."""
        try:
            probe = await self.before_call()
        finally:
            await self._notify()
        try:
            yield
        except StravaUnavailable:
            self.on_failure(probe=probe)
            raise
        except CircuitOpen:
            raise
        except StravaError:
            self.on_success(probe=probe)
            raise
        else:
            self.on_success(probe=probe)
        finally:
            if probe:
                self._probe.release()
            await self._notify()

    async def before_call(self) -> bool:
        """Admit a call or raise `CircuitOpen`. Returns `True` for the half-open probe, which
        holds the probe lock until `guard` releases it."""
        state = self.state
        if state is BreakerState.CLOSED:
            return False
        if state is BreakerState.OPEN:
            raise CircuitOpen(retry_at=self._retry_at())
        if self._probe.locked():
            # Another call is probing; ask again after one more cooldown.
            raise CircuitOpen(retry_at=self._clock() + self.cooldown)
        await self._probe.acquire()  # uncontended: returns without yielding
        if self._state is not BreakerState.HALF_OPEN:
            self._set(BreakerState.HALF_OPEN)
            log.info("circuit_half_open")
        return True

    def on_success(self, *, probe: bool) -> None:
        if probe:
            self._close()
        elif self._state is BreakerState.CLOSED:
            self._failures = 0
        # A call admitted before the circuit opened says nothing about Strava now.

    def on_failure(self, *, probe: bool) -> None:
        if probe:
            self._open()
        elif self._state is BreakerState.CLOSED:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open()

    def _open(self) -> None:
        self._opened_at = self._clock()
        self._set(BreakerState.OPEN)
        log.warning("circuit_opened", failures=self._failures, retry_at=self._retry_at())

    def _close(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._set(BreakerState.CLOSED)
        log.info("circuit_closed")

    def _set(self, state: BreakerState) -> None:
        self._state = state
        self._changed = True
        STRAVA_CIRCUIT_STATE.set(_GAUGE_VALUE[state.value])

    async def _notify(self) -> None:
        if not self._changed or self._listener is None:
            return
        self._changed = False
        retry_at = self._retry_at() if self._state is BreakerState.OPEN else None
        try:
            await self._listener(self._state, retry_at)
        except Exception:
            # Publishing the state is best effort; it must never break a Strava call.
            log.warning("circuit_listener_failed", exc_info=True)

    def _retry_at(self) -> datetime:
        if self._opened_at is None:
            raise RuntimeError("circuit has no open time")
        return self._opened_at + self.cooldown
