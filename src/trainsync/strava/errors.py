"""Typed errors raised by the Strava client.

Names follow docs/architecture.md and docs/diagrams.md, hence the N818 exemptions.
"""

from datetime import datetime


class StravaError(Exception):
    """Base class for every error the Strava client raises."""


class RateLimited(StravaError):  # noqa: N818
    """Strava answered 429 or our own budget denied the call; retry after `reset_at`."""

    def __init__(self, reset_at: datetime) -> None:
        super().__init__(f"rate limited until {reset_at.isoformat()}")
        self.reset_at = reset_at


class CircuitOpen(StravaError):  # noqa: N818
    """The circuit breaker is open; no call was made. Retry after `retry_at`."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__(f"circuit open until {retry_at.isoformat()}")
        self.retry_at = retry_at


class StravaAuthError(StravaError):
    """Credentials were rejected (expired/revoked tokens, bad code, bad client)."""


class StravaUnauthorized(StravaAuthError):  # noqa: N818
    """A single request got 401; the client refreshes once before giving up."""


class StravaNotFound(StravaError):  # noqa: N818
    """The requested object does not exist (404)."""


class StravaRequestError(StravaError):
    """Strava rejected the request with a non-retryable 4xx."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"strava rejected the request with {status_code}")
        self.status_code = status_code


class StravaUnavailable(StravaError):  # noqa: N818
    """Retries were exhausted on network errors, timeouts or 5xx."""
