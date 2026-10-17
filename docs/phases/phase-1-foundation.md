# Phase 1 — Foundation, OAuth, Strava client

Goal: a running stack that can connect a Strava account and make authenticated, resilient calls.

## Tasks
1. Project setup: `uv`, `pyproject.toml`, ruff, mypy, pytest config, `src/` layout from CLAUDE.md.
2. `docker-compose.yml`: postgres, redis, fake-strava, api, worker.
3. Settings with pydantic-settings (`.env.example` committed, `.env` ignored).
4. SQLAlchemy models + first Alembic migration for all tables in `docs/architecture.md`.
5. Fernet token encryption helper.
6. `fake_strava` app: `/oauth/authorize`, `/oauth/token`, `/api/v3/athlete`,
   `/api/v3/athlete/activities`, `/api/v3/activities/{id}`, with seeded fake activities.
   Configurable via env: latency, error rate, rate-limit budget (returns `X-RateLimit-*` headers and 429).
7. OAuth endpoints: login redirect with signed `state`, callback with code exchange.
8. Strava client: shared AsyncClient, timeouts, token refresh with Redis lock, 401 handling,
   retry with exponential backoff + full jitter, rate-limit header parsing.
9. Structured logging + `/health/live`, `/health/ready`.

## Acceptance criteria
- `docker compose up` starts everything; `/health/ready` returns 200.
- Connecting through fake_strava stores an athlete and encrypted tokens.
- Unit tests: backoff timing bounds, retryable vs non-retryable status codes,
  rate-limit header parsing, token refresh race (two concurrent calls → one refresh).
- ruff, mypy, pytest all green.

## Evidence

Phase criteria:

| Criterion | Proven by |
|---|---|
| `docker compose up` starts everything; `/health/ready` returns 200 | `make compose-smoke` (`scripts/compose_smoke.sh`: `up --wait`, then `GET /health/ready`); `tests/integration/test_health_ready.py` |
| Connecting through fake_strava stores an athlete and encrypted tokens | `tests/integration/test_oauth_flow.py::test_connect_stores_athlete_encrypted_tokens_and_enqueues_backfill`; `make compose-smoke` (asserts Fernet ciphertext in `oauth_tokens`) |
| Unit: backoff timing bounds | `tests/unit/test_strava_retry.py::test_backoff_within_full_jitter_bounds`, `::test_backoff_ceiling_grows_then_caps` |
| Unit: retryable vs non-retryable status codes | `tests/unit/test_strava_retry.py` (statuses, transport errors); `tests/unit/test_strava_client.py::test_retries_transient_failures_then_succeeds`, `::test_does_not_retry_client_errors`, `::test_gives_up_after_max_attempts` |
| Unit: rate-limit header parsing | `tests/unit/test_strava_ratelimit.py` |
| Token refresh race (two concurrent calls → one refresh) | `tests/integration/test_tokens.py::test_concurrent_access_token_calls_refresh_once` (real Redis + Postgres + fake_strava, counts `POST /oauth/token`); logic in `tests/unit/test_token_manager.py` |
| ruff, mypy, pytest green | `make verify` |

Task criteria:

| Task | Proven by |
|---|---|
| P1.1 settings, logging, app | `tests/unit/test_settings.py`, `tests/unit/test_logging.py`, `tests/unit/test_app.py`; `uv sync --frozen` |
| P1.2 models, migration, readiness | `tests/integration/test_migrations.py` (round trip, `compare_metadata` no diff, indexes), `tests/integration/test_models.py` (unique, FK cascade, CHECK), `tests/integration/test_health_ready.py` (200, 503 for Redis / DB down, no leak); integration tests are auto-marked by `tests/integration/conftest.py` and excluded by `make test-unit` |
| P1.3 cipher, signed state | `tests/unit/test_crypto.py`, `tests/unit/test_state.py` |
| P1.4 fake_strava | `tests/unit/test_fake_strava.py` (OAuth + rotation, pagination 200/100/[], filters, headers + 429 until quarter hour, error rate, 401, deterministic seed) |
| P1.5 Strava client | `tests/unit/test_strava_client.py`, `tests/unit/test_strava_retry.py`, `tests/unit/test_strava_ratelimit.py`; `::test_only_strava_package_imports_httpx` |
| P1.6 tokens | `tests/integration/test_tokens.py` (ciphertext, race, owner-only release, TTL), `tests/unit/test_token_manager.py` (proactive refresh, rotation, lock released on error, bounded wait), `tests/unit/test_strava_client.py::test_401_refreshes_once_and_retries_once`, `::test_second_401_is_auth_error` |
| P1.7 OAuth endpoints | `tests/unit/test_auth.py` (redirect params, rejections write nothing), `tests/integration/test_oauth_flow.py` (full flow, double callback, reconnect, internal vs public URL) |
| P1.8 compose | `make compose-smoke` (cleans up on failure via `trap`); image runs as uid 10001 (checked in CI `docker` job) |
