import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from trainsync.strava.breaker import BreakerState, CircuitBreaker
from trainsync.strava.errors import (
    CircuitOpen,
    RateLimited,
    StravaNotFound,
    StravaRequestError,
    StravaUnavailable,
)

T0 = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
COOLDOWN = timedelta(seconds=30)


@dataclass
class ManualClock:
    now: datetime = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def breaker(clock: ManualClock) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=5, cooldown=COOLDOWN, clock=clock)


async def fail(breaker: CircuitBreaker, error: Exception | None = None) -> None:
    with pytest.raises(type(error) if error else StravaUnavailable):
        async with breaker.guard():
            raise error or StravaUnavailable("503")


async def succeed(breaker: CircuitBreaker) -> None:
    async with breaker.guard():
        pass


async def trip(breaker: CircuitBreaker) -> None:
    for _ in range(breaker.failure_threshold):
        await fail(breaker)
    assert breaker.state is BreakerState.OPEN


async def test_opens_after_threshold_consecutive_failures(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    for _ in range(4):
        await fail(breaker)
    assert breaker.state is BreakerState.CLOSED
    await fail(breaker)
    assert breaker.state is BreakerState.OPEN

    ran = False
    with pytest.raises(CircuitOpen) as exc_info:
        async with breaker.guard():
            ran = True
    assert not ran
    assert exc_info.value.retry_at == T0 + COOLDOWN


async def test_success_resets_the_failure_count(breaker: CircuitBreaker) -> None:
    for _ in range(4):
        await fail(breaker)
    await succeed(breaker)
    for _ in range(4):
        await fail(breaker)
    assert breaker.state is BreakerState.CLOSED


async def test_stays_open_until_cooldown_has_passed(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN - timedelta(seconds=1))
    assert breaker.state is BreakerState.OPEN
    with pytest.raises(CircuitOpen):
        await succeed(breaker)
    clock.advance(timedelta(seconds=1))
    assert breaker.state is BreakerState.HALF_OPEN


async def test_successful_probe_closes(breaker: CircuitBreaker, clock: ManualClock) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    await succeed(breaker)
    assert breaker.state is BreakerState.CLOSED
    # The failure count starts from zero again.
    for _ in range(4):
        await fail(breaker)
    assert breaker.state is BreakerState.CLOSED


async def test_failed_probe_reopens_for_another_cooldown(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    await fail(breaker)
    assert breaker.state is BreakerState.OPEN
    with pytest.raises(CircuitOpen) as exc_info:
        await succeed(breaker)
    assert exc_info.value.retry_at == clock.now + COOLDOWN


async def test_only_one_probe_while_half_open(breaker: CircuitBreaker, clock: ManualClock) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    probe_started = asyncio.Event()
    release_probe = asyncio.Event()

    async def probe() -> None:
        async with breaker.guard():
            probe_started.set()
            await release_probe.wait()

    task = asyncio.create_task(probe())
    await probe_started.wait()
    for _ in range(3):
        with pytest.raises(CircuitOpen) as exc_info:
            await succeed(breaker)
        assert exc_info.value.retry_at == clock.now + COOLDOWN
    assert breaker.state is BreakerState.HALF_OPEN

    release_probe.set()
    await task
    assert breaker.state is BreakerState.CLOSED
    await succeed(breaker)


async def test_concurrent_callers_get_exactly_one_probe(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    gate = asyncio.Event()

    async def call() -> str:
        try:
            async with breaker.guard():
                await gate.wait()
        except CircuitOpen:
            return "rejected"
        return "probed"

    tasks = [asyncio.create_task(call()) for _ in range(10)]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*tasks)
    assert results.count("probed") == 1
    assert results.count("rejected") == 9


@pytest.mark.parametrize(
    "error",
    [RateLimited(reset_at=T0), StravaRequestError(400), StravaRequestError(403), StravaNotFound()],
    ids=["429", "400", "403", "404"],
)
async def test_client_errors_and_rate_limits_never_open(
    breaker: CircuitBreaker, error: Exception
) -> None:
    for _ in range(20):
        await fail(breaker, error)
    assert breaker.state is BreakerState.CLOSED


async def test_client_error_counts_as_strava_answering(breaker: CircuitBreaker) -> None:
    for _ in range(4):
        await fail(breaker)
    await fail(breaker, StravaNotFound())
    for _ in range(4):
        await fail(breaker)
    assert breaker.state is BreakerState.CLOSED


async def test_probe_answered_with_4xx_closes(breaker: CircuitBreaker, clock: ManualClock) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    await fail(breaker, StravaNotFound())
    assert breaker.state is BreakerState.CLOSED


async def test_unrelated_error_in_probe_frees_the_probe_slot(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    await fail(breaker, ValueError("db down"))
    assert breaker.state is BreakerState.HALF_OPEN
    await succeed(breaker)  # the next call is the probe
    assert breaker.state is BreakerState.CLOSED


async def test_cancelled_probe_frees_the_probe_slot(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    await trip(breaker)
    clock.advance(COOLDOWN)
    started = asyncio.Event()

    async def hang() -> None:
        async with breaker.guard():
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(hang())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await succeed(breaker)
    assert breaker.state is BreakerState.CLOSED


async def test_late_failure_from_before_opening_does_not_extend_cooldown(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    in_flight = asyncio.Event()
    finish = asyncio.Event()

    async def slow_failure() -> None:
        async with breaker.guard():
            in_flight.set()
            await finish.wait()
            raise StravaUnavailable("timeout")

    task = asyncio.create_task(slow_failure())
    await in_flight.wait()
    await trip(breaker)
    clock.advance(timedelta(seconds=10))
    finish.set()
    with pytest.raises(StravaUnavailable):
        await task
    with pytest.raises(CircuitOpen) as exc_info:
        await succeed(breaker)
    assert exc_info.value.retry_at == T0 + COOLDOWN


def test_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=0)
