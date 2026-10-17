# 0006 — Acknowledge, persist, then process webhooks

- Status: accepted
- Date: 2026-10-18

## Context
Strava pushes one small event per change (`object_type`, `object_id`, `aspect_type`,
`event_time`, …) and wants a `200` within 2 seconds. Otherwise it retries a few times and
eventually gives up. The data we actually want (the activity) needs a `GET /activities/{id}`,
which goes through rate limits, retries and the circuit breaker, and can take far longer than
2 seconds when Strava is slow.

## Decision
`POST /webhooks/strava` does only three things, then answers `200`:
1. Validates the body (pydantic). Junk gets `400`. An event for a different
   `subscription_id` gets `200` with `ignored`, so Strava doesn't keep retrying it.
2. Runs `INSERT … ON CONFLICT (dedup_key) DO NOTHING RETURNING id` into `webhook_events`, where
   `dedup_key = sha256(subscription_id:object_type:object_id:aspect_type:event_time)`.
3. Only if a row was inserted, enqueues `process_webhook_event(event_id)` with arq job id
   `webhook:{event_id}`.

The worker does the Strava calls later (ADR 0007). If the enqueue fails after the row was stored
(Redis down), the handler still answers `200`: Strava's retry would be a duplicate and enqueue
nothing, so a `500` would gain us nothing. The webhook retry cron re-enqueues `pending` events that
have waited too long.

## Alternatives considered
- **Process inline**: a Strava fetch inside the handler regularly breaks the 2 s limit under
  retries or rate limits, and violates the rule that the handler makes no Strava calls.
- **Enqueue only, no table**: we would lose dedup across retries and any record of what arrived,
  and an event would be lost when Redis drops it.
- **Dedup on the whole body**: the `updates` map differs between events Strava considers the
  same delivery. The five identifying fields are stable across retries.

## Consequences
- Locally the handler costs one INSERT and one Redis write: p99 ≈ 7 ms over 300 sequential
  requests (`tests/integration/test_webhook_intake.py`).
- `webhook_events` is an inbox and an audit log. Rows are not deleted by the app; pruning old
  `processed` rows is a future operations task.
- Two distinct events about the same activity are both stored and processed. That is fine,
  because processing fetches the current state anyway.
