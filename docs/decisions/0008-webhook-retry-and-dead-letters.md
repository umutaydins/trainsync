# 0008 — Webhook retry cron and dead letters in place

- Status: accepted
- Date: 2026-10-18

## Context
A webhook event can fail during processing (Strava unavailable, a revoked token not yet
followed by the deauth event, a bug), can lose its job (Redis down between the INSERT and the
enqueue, ADR 0006), or can be stuck in `processing` because its worker was killed. The table
must never lose an event silently. A broken event also must not be retried forever.

## Decision
A cron job, `retry_webhooks`, runs every 5 minutes (and at worker startup). Each run takes at
most 200 rows, oldest first:
- `failed` with `attempts < 8`: re-enqueued once `last_attempt_at + min(2^attempts min, 6 h)`
  has passed. The arq job id `webhook:{id}:{attempts}` makes a second sweep a no-op.
- `pending` older than 10 minutes: re-enqueued only if no live arq job exists for it (the
  intake job, or the retry job of this or the previous attempt). A job deferred by the rate
  budget is still live, so it is not duplicated.
- `processing` with `last_attempt_at` older than 10 minutes: set to `failed` (only if it was not
  claimed again meanwhile) and then follows the normal backoff.

Dead letters are `failed` rows with `attempts >= 8`. They stay in `webhook_events`, nothing
retries them, and sync status reports their count. Running the job again by hand means setting
`attempts` back below 8.

`last_attempt_at` (migration 0003) is set on every claim. It drives the backoff and the stuck
check.

## Alternatives considered
- **A separate dead-letter table**: moving rows adds a second write path and loses the single
  view of an event's history. A status plus an attempts threshold is enough at this volume.
- **arq's built-in retries** (`max_tries` + `Retry`): they live in Redis only, so a Redis flush
  or a crash loses them and nothing is left to count. The database is the source of truth.
- **Retry immediately on failure**: retrying while Strava is down just fails again. The
  exponential backoff (2, 4, … 128 min, then 6 h) spreads 8 attempts over about 4 hours.

## Consequences
- An event that keeps failing is parked within about 4 hours and shows up in sync status.
- A lost enqueue is noticed after 10–15 minutes rather than never.
- The cron does one indexed query per run (`status`, `received_at`) plus one Redis lookup per
  stale `pending` row.
