from datetime import UTC, datetime

import pytest

from trainsync.integrations.strava.errors import (
    StravaAuthError,
    StravaRequestError,
    StravaUnauthorized,
    StravaUnavailable,
)
from trainsync.modules.sync.common import short_error
from trainsync.modules.sync.errors import DEAUTHORIZED_ERROR, SyncErrorCode, error_code


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (None, None),
        (short_error(StravaAuthError("refresh token rejected")), SyncErrorCode.STRAVA_AUTH),
        (short_error(StravaUnauthorized("401")), SyncErrorCode.STRAVA_AUTH),
        (DEAUTHORIZED_ERROR, SyncErrorCode.DEAUTHORIZED),
        (short_error(StravaUnavailable("503")), SyncErrorCode.STRAVA_UNAVAILABLE),
        (short_error(StravaRequestError(400)), SyncErrorCode.STRAVA_REJECTED),
        (short_error(KeyError("athlete")), SyncErrorCode.INTERNAL),
        ("something nobody planned for", SyncErrorCode.INTERNAL),
    ],
)
def test_stored_errors_map_to_codes(error: str | None, code: SyncErrorCode | None) -> None:
    assert error_code(error) == code


def test_a_timestamped_message_keeps_its_code() -> None:
    message = f"StravaAuthError: expired at {datetime(2026, 10, 1, tzinfo=UTC).isoformat()}"
    assert error_code(message) is SyncErrorCode.STRAVA_AUTH
