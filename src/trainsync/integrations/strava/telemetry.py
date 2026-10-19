"""Per-call metrics and the `strava_call` log line (endpoint template, status, duration, attempt).
The logger keeps the client's name, so log queries on `strava_call` still match."""

import time

from trainsync.core.logging import get_logger
from trainsync.core.metrics import STRAVA_REQUEST_DURATION, STRAVA_REQUESTS

log = get_logger("trainsync.integrations.strava.client")

MS_PER_SECOND = 1000


def log_call(
    template: str,
    status: int | None,
    started: float,
    attempt: int,
    *,
    error: str | None = None,
) -> None:
    duration = time.perf_counter() - started
    STRAVA_REQUESTS.labels(template, "error" if status is None else str(status)).inc()
    STRAVA_REQUEST_DURATION.labels(template).observe(duration)
    log.info(
        "strava_call",
        endpoint=template,
        status=status,
        duration_ms=round(duration * MS_PER_SECOND, 1),
        attempt=attempt + 1,
        error=error,
    )
