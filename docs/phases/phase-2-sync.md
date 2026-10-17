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
