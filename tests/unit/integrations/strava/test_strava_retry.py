import random

import httpx
import pytest

from trainsync.integrations.strava.retry import RetryPolicy, is_retryable


def test_backoff_within_full_jitter_bounds() -> None:
    policy = RetryPolicy(max_attempts=4, base=0.5, cap=8.0)
    rng = random.Random(1)
    for attempt in range(10):
        ceiling = min(8.0, 0.5 * 2**attempt)
        samples = [policy.backoff(attempt, rng) for _ in range(2000)]
        assert all(0 <= s <= ceiling for s in samples)
        # full jitter spreads over the whole range, not just near the ceiling
        assert min(samples) < ceiling * 0.05
        assert max(samples) > ceiling * 0.95


def test_backoff_ceiling_grows_then_caps() -> None:
    policy = RetryPolicy(base=0.5, cap=8.0)
    assert [policy.ceiling(a) for a in range(7)] == [0.5, 1, 2, 4, 8, 8, 8]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_statuses(status: int) -> None:
    assert is_retryable(httpx.Response(status))


@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 422])
def test_non_retryable_statuses(status: int) -> None:
    assert not is_retryable(httpx.Response(status))


@pytest.mark.parametrize(
    "exc",
    [httpx.ConnectError("x"), httpx.ReadTimeout("x"), httpx.PoolTimeout("x"), httpx.ReadError("x")],
)
def test_transport_errors_are_retryable(exc: Exception) -> None:
    assert is_retryable(exc)


def test_other_exceptions_are_not_retryable() -> None:
    assert not is_retryable(ValueError("x"))
