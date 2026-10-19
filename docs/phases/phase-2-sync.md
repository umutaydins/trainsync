# Phase 2 — Sync engine

Goal: full history and ongoing changes land in PostgreSQL reliably.

## Tasks
1. arq worker with job functions: `backfill(athlete_id)`, `incremental_sync(athlete_id)`.
2. Backfill with pagination, per-page transaction, cursor checkpoint in `sync_runs`.
3. Idempotent activity upsert (`INSERT ... ON CONFLICT (strava_activity_id) DO UPDATE`).
4. Incremental sync cron (every 30 min) with 2-day overlap window.
5. Rate-limit budget in Redis with two priorities (backfill = low, webhook = high).
   Low priority pauses above 80% of the 15-minute budget; 429 waits for the window reset.
6. Circuit breaker in the Strava client; open circuit → job re-enqueued with delay.

## Acceptance criteria
- Backfill of 1,000 fake activities completes; running it twice changes nothing.
- Killing the worker mid-backfill and restarting resumes from the cursor (integration test).
- With fake_strava at a low rate-limit budget, backfill pauses and resumes without a 429 storm.
- With fake_strava at 50% errors, the circuit opens, jobs are delayed, and all data arrives once errors stop.
- Integration tests run against testcontainers Postgres + Redis + fake_strava.

## Evidence

Phase criteria (all integration tests run against testcontainers Postgres 16 + Redis 7 and
fake_strava; see `tests/integration/conftest.py`):

| Criterion | Proven by |
|---|---|
| Backfill of 1,000 fake activities completes; running it twice changes nothing | `tests/integration/modules/sync/test_backfill.py::test_backfill_stores_everything_once` (1,000 rows, `succeeded` run, second run upserts 0); `tests/integration/modules/activities/test_activity_repository.py::test_upsert_is_idempotent` (`synced_at` unchanged) |
| Killing the worker mid-backfill and restarting resumes from the cursor | `tests/fault/test_worker_restart.py::test_sigkilled_worker_backfill_resumes_from_cursor` (moved to the fault suite in P4.2; `make test-fault`) (real `arq` worker process SIGKILLed after 2 pages, fake_strava under uvicorn; a new worker finishes the **same** run and only fetches the pages after the checkpoint); `tests/integration/modules/sync/test_backfill.py::test_cancelled_backfill_resumes_from_cursor` (graceful cancel → `paused`, pages fetched ≤ needed + 1), `::test_stale_running_run_is_taken_over_live_one_is_not` |
| Low rate-limit budget: backfill pauses and resumes without a 429 storm | `tests/integration/integrations/strava/test_rate_budget.py::test_backfill_pauses_before_429_and_completes_across_windows` (`RATE_LIMIT_15MIN=50`, ≤ 1 429 in fake_strava stats), `::test_high_priority_fetch_still_works_while_backfill_is_paused` |
| 50% errors: circuit opens, jobs delayed, all data arrives once errors stop | `tests/integration/integrations/strava/test_circuit_breaker.py::test_flaky_strava_opens_circuit_defers_jobs_and_recovers` (`ERROR_RATE=0.5` via `/_control/config`; every run ends `paused` + deferred, never failed; with the circuit open the job is deferred to `retry_at` with no request sent; after `ERROR_RATE=0` all 1,000 activities are stored exactly once). Checked with fake_strava seeds 1–10. |
| Integration tests use testcontainers + fake_strava | `tests/integration/conftest.py` (`PostgresContainer`, `RedisContainer`, Alembic `upgrade head`); fake_strava in-process via `httpx.ASGITransport` (`tests/conftest.py`) or as a uvicorn process (`tests/support/fake_server.py`) |

Task criteria:

| Task | Proven by |
|---|---|
| P2.1 worker, upsert | `tests/integration/entrypoints/worker/test_worker.py` (lifecycle closes engine + httpx client; `arq` CLI starts and exits); `tests/integration/modules/activities/test_activity_repository.py` (idempotent 200 → 0, one changed field → one row, soft-deleted row restored, duplicates in one batch) |
| P2.2 resumable backfill | `tests/integration/modules/sync/test_backfill.py` (1,000 rows once, cancel/resume with page count via `/_control/stats`, boundary-second ties, `RateLimited` → `paused` + `Retry` defer ≈ reset, budget denial, auth / unexpected errors, inactive athlete) |
| P2.3 incremental cron | `tests/integration/modules/sync/test_incremental.py` (edit 1 day ago, late upload inside window, pagination, paused run resumes, needs-backfill, skips, one job per athlete per window) |
| P2.4 rate budget | `tests/unit/integrations/strava/test_budget.py` (thresholds, stale window, daily exhaustion, after 429); `tests/integration/integrations/strava/test_rate_budget.py` (Redis round trip, ≤ 1 429, high priority while paused); `tests/unit/integrations/strava/test_strava_client.py::test_429_*` |
| P2.5 circuit breaker | `tests/unit/integrations/strava/test_breaker.py` (threshold, cooldown, single probe incl. 10 concurrent callers, probe success closes, probe failure reopens, 4xx/429 never open, cancelled probe frees the slot); `tests/unit/integrations/strava/test_strava_client_breaker.py` (5xx / timeouts open the circuit, open → no HTTP request, 4xx/401/429 never open, budget denial ignored); `tests/integration/integrations/strava/test_circuit_breaker.py`; `tests/integration/modules/sync/test_backfill.py::test_strava_unavailable_pauses_instead_of_failing` |
| All | `make verify` |
