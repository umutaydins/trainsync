"""Prometheus metrics (names fixed in docs/phases/phase-4-reliability-ci.md).

Every process has its own registry, the default one. The API serves it at `/metrics`, and each
worker serves it on `WORKER_METRICS_PORT` (ADR 0010). Labels stay low-cardinality: endpoint
*templates*, route *templates*, status codes, a handful of enum values.
"""

from prometheus_client import Counter, Gauge, Histogram

STRAVA_REQUESTS = Counter(
    "strava_requests_total",
    "HTTP requests sent to Strava, one per attempt",
    ["endpoint", "status"],
)
STRAVA_REQUEST_DURATION = Histogram(
    "strava_request_duration_seconds",
    "Duration of one HTTP attempt to Strava",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
STRAVA_RETRIES = Counter("strava_retries_total", "Retried Strava attempts (5xx, timeouts)")
STRAVA_CIRCUIT_STATE = Gauge(
    "strava_circuit_state", "Circuit breaker of this process: 0 closed, 1 half_open, 2 open"
)
STRAVA_RATELIMIT_USAGE = Gauge(
    "strava_ratelimit_usage_ratio",
    "Share of Strava's rate limit used, from the latest response",
    ["window"],
)
SYNC_JOBS = Counter("sync_jobs_total", "Finished sync job runs", ["kind", "status"])
WEBHOOK_EVENTS = Counter(
    "webhook_events_total",
    "Webhook events received (queued/duplicate/ignored) and processed (outcome)",
    ["aspect", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "API request duration by route template",
    ["route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


def webhook_aspect(object_type: str, aspect_type: str) -> str:
    """`activity:create`, `athlete:update`, … (6 values at most)."""
    return f"{object_type}:{aspect_type}"


# ---------------------------------------------------------------- bot + notifications (Phase 5)
# The bot is its own process and serves these on BOT_METRICS_PORT (ADR 0010).
BOT_UPDATES = Counter(
    "bot_updates_total",
    "Telegram updates handled by the bot, by command (a fixed set) and outcome",
    ["command", "outcome"],
)
