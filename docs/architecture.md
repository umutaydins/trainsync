# Architecture

## Purpose

Keep a complete, always-fresh copy of my Strava activities in my own PostgreSQL database
and expose it through my own API (filters, weekly stats), without depending on Strava
being up or my rate-limit budget being available at read time.

## Components

```
                ┌─────────────────────────── trainsync ───────────────────────────┐
 Strava  ──webhook POST──▶  API (FastAPI)  ──enqueue──▶  Redis (arq queue)        │
   ▲                         │   ▲                           │                    │
   │                         │   └── read API ◀── PostgreSQL ◀── upsert ──┐       │
   │                         │                                           │       │
   └──── HTTPS (httpx) ◀── Strava client ◀── Worker (arq jobs + cron) ───┘       │
          rate limiter · retries · circuit breaker · token refresh               │
                └────────────────────────────────────────────────────────────────┘
```

- **API process**: OAuth endpoints, webhook endpoints, read API, health, metrics.
- **Worker process**: backfill, incremental sync, webhook event processing, scheduled jobs.
- **Strava client**: the only place that talks to Strava. Owns auth headers, token refresh,
  retries, rate-limit accounting and the circuit breaker.
- **fake_strava**: a small FastAPI app that mimics the endpoints we use, with configurable
  latency, error rate and rate-limit headers. Used for local dev, integration tests and load tests.

## Data model

| Table | Key columns | Notes |
|---|---|---|
| `athletes` | `id`, `strava_athlete_id` (unique), `active`, `created_at` | `active=false` after deauthorization |
| `oauth_tokens` | `athlete_id` (PK/FK), `access_token_enc`, `refresh_token_enc`, `expires_at`, `scope` | encrypted with Fernet |
| `activities` | `id`, `strava_activity_id` (unique), `athlete_id`, `name`, `sport_type`, `start_date` (timestamptz), `distance_m`, `moving_time_s`, `elapsed_time_s`, `elevation_gain_m`, `average_heartrate` (nullable), `raw` (jsonb), `deleted_at` (nullable), `synced_at` | upsert on `strava_activity_id`; soft delete |
| `sync_runs` | `id`, `athlete_id`, `kind` (backfill / incremental), `status`, `cursor` (jsonb), `pages`, `upserted`, `error`, `started_at`, `updated_at`, `finished_at` | `cursor` makes backfill resumable; `updated_at` is a per-page heartbeat |
| `webhook_events` | `id`, `dedup_key` (unique), `payload` (jsonb), `status`, `attempts`, `received_at`, `last_attempt_at`, `processed_at` | dedup on (subscription_id, object_type, object_id, aspect_type, event_time) |

Indexes: `activities (athlete_id, start_date desc)`, `activities (athlete_id, sport_type, start_date)`,
`webhook_events (status, received_at)`.

## Flows

### 1. OAuth connect
1. `GET /auth/strava/login` redirects to Strava authorize URL with `scope=read,activity:read_all` and a signed `state`.
2. `GET /auth/strava/callback` verifies `state`, exchanges `code` for tokens, upserts athlete + encrypted tokens.
3. Enqueues a `backfill` job.

### 2. Token refresh
- Before each Strava call: if `expires_at - 5 min < now`, refresh.
- On a 401: refresh once, retry once, then fail.
- Refresh is guarded by a per-athlete Redis lock, because concurrent jobs refreshing at the same
  time would race and one of them could end up storing a stale refresh token.
- Always persist the refresh token returned by Strava (it can change).

### 3. Strava client: retries, rate limits, circuit breaker
- **Timeouts**: connect 3 s, read 10 s, pool 5 s.
- **Retries**: only for network errors, timeouts, 5xx and 429. Exponential backoff with full jitter,
  max 4 attempts. Never retry other 4xx.
- **Rate limits**: Strava returns `X-RateLimit-Limit` and `X-RateLimit-Usage` as `"<15min>,<daily>"`.
  Parse them on every response and store the latest values in Redis. Do not hard-code the limits.
  - Above 80% of the 15-minute budget, low-priority work (backfill) pauses until the next window;
    webhook-driven fetches keep going. This is a two-priority budget.
  - On 429, wait until the next 15-minute window boundary (check Strava docs for reset rules)
    instead of hammering with retries.
- **Circuit breaker** (per process): opens after N consecutive 5xx / timeouts, half-opens after a
  cooldown and lets one probe request through. While open, jobs are re-queued with a delay
  instead of failing. 4xx and 429 mean Strava answered, so they count as successes. A sync job
  that gets `StravaUnavailable` while the circuit is still closed is also paused and deferred
  (30 s) instead of failed. See ADR 0005.
- Metrics for every call: endpoint, status, duration, retry count.

### 4. Backfill
- Paginate `GET /athlete/activities?per_page=200&page=N` (or `before=` timestamp cursor).
- Upsert each page in one transaction, then persist the cursor in `sync_runs.cursor`.
- If the worker dies or the rate budget runs out, the next run resumes from the cursor.
- Cursor = oldest `start_date` on the page + 1 s (always `page=1`), so activities sharing the
  boundary second are re-fetched instead of skipped; the history is done on an empty page or when
  a short page makes no progress.
- One backfill per athlete: arq job id `backfill:{athlete_id}`, and a `running` run whose
  `updated_at` heartbeat is younger than 5 minutes is left alone (older = its worker died → resume).

### 5. Incremental sync (cron, every 30 min)
- `after = max(start_date) - 2 days` overlap window to catch late edits and uploads.
- Same upsert path as backfill. Safety net for missed webhooks.

### 6. Webhooks
- `GET /webhooks/strava`: subscription validation. Check `hub.verify_token`,
  respond `{"hub.challenge": "<value>"}` with 200.
- `POST /webhooks/strava`: must return 200 within 2 seconds (Strava retries up to 3 times otherwise).
  - Validate `subscription_id`.
  - `INSERT ... ON CONFLICT (dedup_key) DO NOTHING` into `webhook_events`.
  - Enqueue `process_webhook_event(event_id)` and return 200 immediately.
- Worker processing:
  - `activity create/update` → fetch `GET /activities/{id}` and upsert. Use the fetched data,
    not the event, so out-of-order events end in the correct final state.
  - `activity delete` → soft delete.
  - `athlete update` with `authorized=false` → mark athlete inactive, delete tokens and the
    athlete's activities.
- Failed events stay in `webhook_events` with `status=failed` and `attempts`. A cron job retries them
  with backoff. This acts as a simple dead-letter table. The same cron (every 5 min) re-enqueues
  `pending` events older than 10 minutes that have no live job, and releases events stuck in
  `processing` for over 10 minutes. After 8 attempts an event is a dead letter (ADR 0008).

### 7. Read API (API key in `X-API-Key` header)
- `GET /v1/activities?from=&to=&sport_type=&limit=&cursor=`: keyset pagination on `(start_date, id)`.
- `GET /v1/stats/weekly?from=&to=&sport_type=`: per ISO week distance, moving time, elevation, count
  (SQL aggregation).
- `GET /v1/sync/status`: last sync runs, last webhook, webhook retry and dead-letter counts, current
  rate-limit usage, circuit state of every process (each publishes its breaker transitions to Redis).
- Responses include `last_synced_at`, so the client knows how fresh the data is when Strava is degraded.

### 8. Operations
- `GET /health/live` (process up), `GET /health/ready` (DB + Redis reachable).
- `GET /metrics` Prometheus endpoint.
- JSON logs with `request_id` / `job_id` correlation.

## Failure modes this design handles

| Failure | Behavior |
|---|---|
| Strava 5xx / timeouts | retries with backoff → circuit opens → jobs delayed, reads unaffected |
| Rate limit near / exceeded | backfill pauses, webhooks still processed; 429 waits for window reset |
| Worker crash mid-backfill | resumes from persisted cursor; upserts are idempotent |
| Duplicate webhook delivery | dedup key, `ON CONFLICT DO NOTHING` |
| Out-of-order webhook events | worker always fetches the current activity state |
| Missed webhooks | incremental sync with an overlap window |
| Expired / rotated tokens | proactive refresh, 401 retry, per-athlete lock |
| User revokes access | deauth event → tokens and data removed |
