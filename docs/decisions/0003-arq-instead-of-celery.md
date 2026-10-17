# 0003 — arq instead of Celery

- Status: accepted
- Date: 2026-10-18

## Context
The worker runs backfill, incremental sync and webhook processing. All of it is I/O-bound
(Strava over HTTPS, PostgreSQL, Redis) and the codebase is async end to end (FastAPI, httpx
`AsyncClient`, SQLAlchemy async). Redis is already required for the refresh lock and the rate
budget. This is a single-user service on small hardware.

## Decision
Use arq: asyncio-native jobs and cron on Redis. Job functions are plain `async def` functions
that reuse the same async client, engine and token manager as the API code. We rely on:
- `_job_id` for deduplication (`backfill:{athlete_id}`, `incremental:{athlete_id}:{window}`,
  `webhook:{event_id}`) — enqueueing an id that is queued, running or has a kept result is a no-op;
- `_defer_until` / `Retry(defer=…)` to park a job until the rate-limit window resets or the
  circuit breaker's cooldown ends;
- `arq.cron` for the 30-minute incremental sync and the webhook retry sweep.

## Alternatives considered
- Celery — mature and feature-rich (priorities, routing, canvas), but sync-first: async code needs
  an event loop per task or a separate pool, and it adds a broker/result-backend setup we don't need.
- Dramatiq — simpler than Celery, still thread/sync-oriented.
- RQ — sync only.
- A hand-rolled queue on PostgreSQL (`SKIP LOCKED`) — fewer moving parts, but we would reimplement
  deferral, retries and cron.

## Consequences
- Small footprint, one event loop per worker, shared resources created once in `on_startup`.
- arq has no task priorities. Priority lives in the rate budget instead (see ADR 0004): low-priority
  sync jobs defer themselves, webhook jobs keep going.
- `Retry` deferrals count towards arq's `job_try`; sync jobs that may wait out many rate-limit
  windows get a generous `max_tries`, and real failures are tracked in `sync_runs` / `webhook_events`
  rather than through arq retries.
- Job results are kept for an hour, which also blocks re-enqueueing the same job id in that time;
  job ids are chosen with that in mind.
