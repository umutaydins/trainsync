"""Retry policy: exponential backoff with full jitter."""

import random
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    base: float = 0.5
    cap: float = 8.0

    def ceiling(self, attempt: int) -> float:
        """Upper bound of the delay after the `attempt`-th failure (0-based)."""
        return min(self.cap, self.base * 2.0**attempt)

    def backoff(self, attempt: int, rng: random.Random) -> float:
        """Full jitter: uniform(0, min(cap, base * 2**attempt))."""
        return rng.uniform(0, self.ceiling(attempt))


def is_retryable(outcome: httpx.Response | BaseException) -> bool:
    """Network errors, timeouts, 5xx and 429 are retryable; any other 4xx is not."""
    if isinstance(outcome, BaseException):
        return isinstance(outcome, httpx.TransportError)
    return outcome.status_code == 429 or outcome.status_code >= 500
