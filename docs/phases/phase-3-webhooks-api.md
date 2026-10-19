# Phase 3 — Webhooks and read API

Goal: near-real-time updates and a useful API on top of the data.

## Tasks
1. `GET /webhooks/strava` subscription validation (`hub.verify_token`, echo `hub.challenge`).
2. `POST /webhooks/strava`: validate, dedup insert into `webhook_events`, enqueue, return 200.
3. `process_webhook_event` job: create/update → fetch + upsert, delete → soft delete,
   deauthorization → deactivate athlete, remove tokens and activities.
4. Retry cron for failed webhook events (simple dead-letter handling).
5. fake_strava: endpoint to fire webhook events at the service (single, duplicate, out-of-order bursts).
6. Read API with `X-API-Key` auth:
   - `GET /v1/activities` with filters and keyset pagination
   - `GET /v1/stats/weekly`
   - `GET /v1/sync/status`

## Acceptance criteria
- Webhook POST p99 < 100 ms locally (it only writes and enqueues).
- Duplicate events are processed once; out-of-order create/update/delete ends in the correct state.
- Deauthorization removes the athlete's tokens and data.
- Weekly stats match a hand-computed fixture.
- OpenAPI docs at `/docs` describe every endpoint with examples.

## Evidence

Phase criteria (integration tests run against testcontainers Postgres 16 + Redis 7; fake_strava
delivers webhooks straight into the trainsync app over an ASGI transport):

| Criterion | Proven by |
|---|---|
| Webhook POST p99 < 100 ms locally | `tests/integration/modules/sync/test_webhook_intake.py::test_p99_latency_under_100ms` (300 sequential POSTs, prints p50/p99; measured p99 ≈ 7 ms); `::test_handler_makes_no_outbound_http_calls` |
| Duplicate events are processed once | `tests/integration/modules/sync/test_webhook_intake.py::test_same_event_five_times_stores_one_row_and_one_job`; `tests/integration/modules/sync/test_webhook_processing.py::test_duplicate_deliveries_are_processed_once` (5 deliveries → 1 row → 1 fetch in fake_strava stats) |
| Out-of-order create/update/delete ends in the correct state | `tests/integration/modules/sync/test_webhook_processing.py::test_out_of_order_update_and_delete_of_a_synced_activity_soft_deletes`, `::test_out_of_order_lifecycle_of_a_new_activity_leaves_nothing_visible`, `::test_create_and_update_in_reverse_order_end_with_latest_title` |
| Deauthorization removes the athlete's tokens and data | `tests/integration/modules/sync/test_webhook_processing.py::test_deauthorization_removes_tokens_and_data` (via fake_strava's deauthorize scenario; later events are ignored without fetching); `tests/integration/modules/sync/test_backfill.py::test_deauthorization_mid_backfill_writes_nothing_back` |
| Weekly stats match a hand-computed fixture | `tests/integration/modules/stats/test_stats_and_status.py::test_weekly_stats_match_hand_computed_fixture` with `tests/fixtures/weekly_stats.json` (Sunday 23:30 / Monday 00:30 boundary, empty week, soft-deleted row, out-of-range rows) |
| OpenAPI docs at `/docs` describe every endpoint with examples | `tests/unit/entrypoints/api/test_openapi.py` (summary, tag and an example for every request/response body including errors; `/docs` served; `docs/openapi.json` current via `scripts/export_openapi.py`) |

Task criteria:

| Task | Proven by |
|---|---|
| P3.1 webhook endpoints | `tests/unit/modules/sync/test_webhooks_api.py` (challenge echo, 403 for wrong token/mode, 400 for junk, other subscription ignored, dedup key fields); `tests/integration/modules/sync/test_webhook_intake.py` (5× → 1 row + 1 job, no outbound HTTP, enqueue failure still 200, p99) |
| P3.2 fake webhook sender | `tests/unit/fake_strava/test_fake_webhooks.py` (single / duplicate / seeded out-of-order, retry on 500, give up after 3, retry on slow target, concurrency, lifecycle scenario consistent with fake state, deauthorize scenario) |
| P3.3 event processing | `tests/integration/modules/sync/test_webhook_processing.py` (all of the above, unknown owner, fetch while backfill is paused by the budget, open circuit → `pending` + deferred job, other errors → `failed`, processed events not reclaimed) |
| P3.4 retry cron | `tests/integration/modules/sync/test_webhook_retry.py` (2/4/8-minute backoff with injected clock until fake_strava recovers, 8 attempts → dead letter, stale `pending` without job recovered and not duplicated, stuck `processing` released) |
| P3.5 activities API | `tests/unit/modules/activities/test_activities_api.py` (401 + `WWW-Authenticate`, invalid cursors → 400, limit bounds); `tests/integration/modules/activities/test_activities_api.py` (1,000 rows paged at 200 with inserts between pages: each once, in order; filter combinations; soft-deleted / inactive excluded; `EXPLAIN` over 60,000 rows uses `ix_activities_athlete_start_date`) |
| P3.6 stats and status | `tests/integration/modules/stats/test_stats_and_status.py` (fixture, sport filter, zero-filled weeks, partial edge weeks, default range, bad ranges; status with a running backfill, failed + dead-letter webhooks, 82% budget and an open circuit published by a worker); `tests/unit/integrations/strava/test_breaker_status.py`, `tests/unit/integrations/strava/test_breaker.py::test_listener_*` |
| P3.7 OpenAPI | `tests/unit/entrypoints/api/test_openapi.py` |
| All | `make verify` |
