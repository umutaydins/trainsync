"""What a failed run's error means for the person reading it.

A run stores its error as `"<ExceptionName>: <message>"` (`common.short_error`). The status API
turns that into a stable code the web app translates; the raw text stays technical detail for the
owner only.
"""

from enum import StrEnum

from trainsync.integrations.strava.errors import (
    StravaAuthError,
    StravaNotFound,
    StravaRequestError,
    StravaUnauthorized,
    StravaUnavailable,
)
from trainsync.modules.strava.tokens import TokenRefreshTimeoutError

# Stored when the athlete is deauthorized while their sync runs (`common.run_guarded`).
DEAUTHORIZED_ERROR = "athlete deauthorized during sync"


class SyncErrorCode(StrEnum):
    STRAVA_AUTH = "strava_auth"
    DEAUTHORIZED = "deauthorized"
    STRAVA_UNAVAILABLE = "strava_unavailable"
    STRAVA_REJECTED = "strava_rejected"
    INTERNAL = "internal"


_BY_EXCEPTION: dict[str, SyncErrorCode] = {
    **dict.fromkeys(
        (StravaAuthError.__name__, StravaUnauthorized.__name__), SyncErrorCode.STRAVA_AUTH
    ),
    **dict.fromkeys(
        (StravaUnavailable.__name__, TokenRefreshTimeoutError.__name__),
        SyncErrorCode.STRAVA_UNAVAILABLE,
    ),
    **dict.fromkeys(
        (StravaRequestError.__name__, StravaNotFound.__name__), SyncErrorCode.STRAVA_REJECTED
    ),
}


def error_code(error: str | None) -> SyncErrorCode | None:
    """The code of a stored run error; anything unknown is `internal`."""
    if error is None:
        return None
    if error == DEAUTHORIZED_ERROR:
        return SyncErrorCode.DEAUTHORIZED
    name = error.split(":", 1)[0].strip()
    return _BY_EXCEPTION.get(name, SyncErrorCode.INTERNAL)
