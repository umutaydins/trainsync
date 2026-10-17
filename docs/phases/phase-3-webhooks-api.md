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
