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
- **Worker process**: backfill, incremental sync, webhook event processing, scheduled jobs
  (including the evening check-in prompt).
- **Strava client**: the only place that talks to Strava. Owns auth headers, token refresh,
  retries, rate-limit accounting and the circuit breaker.
- **Bot process** (`python -m trainsync.bot`, Phase 5): Telegram long polling, deterministic
  summary commands, training/nutrition commands and the daily check-in (Phase 6), chat allowlist. A client of the read API (HTTP + API key), never of the
  database (ADR 0012, ADR 0013). Optional natural-language questions: Claude chooses read-API
  calls through four validated tools, every number comes from the API (ADR 0014). All wording
  (replies, notifications, the assistant's persona) comes from a message pack chosen by
  `BOT_TONE` × `BOT_LANG` (ADR 0016). `BOT_INTENSITY=savage` adds the owner's opt-in brutal
  coach (savage line pack, excuse roasts, timed messages from the worker), and hard guardrails
  (body, slurs, pain/illness, food) hold in every intensity (ADR 0030).
- **Web dashboard** (`web/`, Next.js): server-side BFF that holds the API key and forwards
  allowlisted method + path combinations to the API (reads, and CSRF-checked JSON writes to
  training, nutrition and check-ins); the browser never sees the key (ADR 0011). Phase 6 pages:
  `/training` (today, programs, the active-workout screen, history, progress) and `/nutrition`;
  installable as a PWA without a service worker (ADR 0021).
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
| `notifications` | `id`, `kind` (`new_activity`, `checkin_prompt`, `checkin_reminder`), `object_id`, `sent_at`; unique (`kind`, `object_id`) | claimed before sending, released on a failed send (ADR 0012); check-in kinds use the local date `yyyymmdd` as `object_id` (ADR 0020) |

Indexes: `activities (athlete_id, start_date desc)`, `activities (athlete_id, sport_type, start_date)`,
`webhook_events (status, received_at)`.

Training (Phase 6, single user, no `athlete_id`):

| Table | Key columns | Notes |
|---|---|---|
| `exercises` | `id`, `slug` (unique), `name`, `primary_muscle`, `secondary_muscles` (text[]), `equipment`, `movement_pattern` (nullable), `is_custom`, `created_at` | ~70 built-in rows seeded by migration 0005 from `training/seed_exercises.json`; `movement_pattern` feeds the program generator |
| `programs` | `id`, `name`, `goal` (strength / hypertrophy / general), `days_per_week`, `weeks`, `active`, `created_at` | partial unique index: at most one active program |
| `program_days` | `id`, `program_id` (FK cascade), `day_index`, `name`, `weekday` (0–6, nullable), `start_time` (nullable); unique (`program_id`, `day_index`) | `weekday`/`start_time` drive the coach's reminders; null = default spread and `WORKOUT_REMINDER_TIME` (ADR 0030) |
| `program_exercises` | `id`, `program_day_id` (FK cascade), `exercise_id`, `position`, `sets`, `rep_min`, `rep_max`, `rest_seconds`, `start_weight_kg`, `progression` | |
| `workouts` | `id`, `client_id` (uuid, unique), `program_day_id` (nullable, set null), `started_at`, `ended_at`, `notes`, `strava_activity_id` (link, no FK) | started with `PUT` by `client_id`: a retried start is one workout (ADR 0017) |
| `workout_sets` | `id`, `client_id` (uuid, unique), `workout_id` (FK cascade), `exercise_id`, `set_index`, `reps`, `weight_kg` numeric(6,2), `rpe`, `is_warmup`, `completed_at`, `rest_seconds` | upsert on `client_id`: a retried log is one row |
| `body_metrics` | `date` (PK), `weight_kg` | only what the user enters |
| `daily_checkins` | `id`, `date` (unique, local day), `status` (done / partial / skipped / rest / sick_or_injured), `workout_id` (nullable, set null), `reason_note`, `sleep_hours`, `energy_1_5`, `body_weight_kg`, `created_at`, `updated_at` | upsert on `date`; a body weight is also written to `body_metrics` (P6.9, ADR 0020) |

Training math (`training/math.py`): volume = reps × weight without warm-ups; Epley e1RM for 1–12
reps (none above); records per exercise for weight at a rep count, e1RM and session volume.

Nutrition (Phase 6, P6.4, single user, no `athlete_id`; ADR 0019):

| Table | Key columns | Notes |
|---|---|---|
| `foods` | `id`, `name`, `brand`, `barcode` (unique, nullable), `kcal_100g` numeric(6,1), `protein_100g` / `carbs_100g` / `fat_100g` (numeric(5,1), nullable = unknown), `source` (manual / openfoodfacts), `favorite`, `created_at` | Open Food Facts results are cached here, upserted on `barcode`; editing a cached row turns it `manual`, so later lookups leave it alone |
| `food_logs` | `id`, `client_id` (uuid, unique), `date`, `meal` (breakfast / lunch / dinner / snack), `food_id` (FK), `grams` numeric(6,1), `kcal_100g`, `protein_100g`, `carbs_100g`, `fat_100g` (snapshot of the food at log time), `created_at` | upsert on `client_id`: a retried log is one row; summaries read the snapshot, so editing a food never changes past days; index (`date`, `meal`) |
| `nutrition_profile` | `id` (always 1), `sex`, `birth_year`, `height_cm`, `activity_baseline` (sedentary / light / moderate), `kcal_target`, `protein_target_g`, `updated_at` | one row; body weight is not here, it comes from `body_metrics` |

Energy balance (`nutrition/energy.py`, pure, all values are estimates; `nutrition/summary.py` reads
the tables):
- **Days are UTC days**, like the rest of the read API: an activity counts on the UTC date of its
  `start_date`; a food log on the `date` the client sent.
- **BMR**: Mifflin–St Jeor (`10w + 6.25h − 5a + 5`, female `− 161`), `w` = latest `body_metrics`
  weight on or before the day, `a` = day's year − birth year. No profile or no weight → BMR,
  baseline, expenditure and balance are null and `estimate_unavailable_reason` says why
  (`no_profile` / `no_body_weight`). Nothing is guessed.
- **Baseline** = BMR × 1.2 / 1.375 / 1.55 (everyday activity, logged exercise excluded).
- **Exercise** per activity of active athletes, soft-deleted excluded: `raw.calories` when > 0, else
  for `sport_type` containing `Ride` `raw.kilojoules` (≈ kcal), else unknown (`kcal: null`,
  `kcal_known: false`). Known values are summed into `exercise_kcal`; unknowns are counted
  (`exercise_unknown_count`, `exercise_complete`).
- **Balance** = intake − (baseline + known exercise); `balance_complete` is false when an activity's
  energy is unknown or there is no baseline. kcal and grams are rounded to 0.1 at the end.
- A `kcal_target` below the estimated BMR is stored as entered and the profile answers with a
  neutral `warning`; the API never suggests a deficit.

Endpoints (`/v1/nutrition`, API key): `GET/POST /foods`, `GET /foods/lookup?barcode=|q=`,
`PATCH /foods/{id}`, `PUT/DELETE /foods/{id}/favorite`, `GET /log?date=`,
`PUT/DELETE /log/{client_id}` (PUT → 201 created / 200 updated), `GET/PUT /profile`,
`GET /summary?date=`, `GET /summary/weekly?from=&to=` (default: current ISO week, ≤ 92 days).

Open Food Facts (`nutrition/off_client.py`, the only module that calls it): public API, no key,
`OPENFOODFACTS_USER_AGENT`, the process's shared `httpx.AsyncClient` with a 3 s whole-request
timeout, no retries. Timeouts, network errors and non-200/404 answers → the lookup still answers
with local matches and `remote: "unavailable"`; `OPENFOODFACTS_ENABLED=false` → `remote: "disabled"`.
The remote call happens outside any DB session, so a slow lookup never holds a connection.

## Flows

### 1. OAuth connect
1. `GET /auth/strava/login` redirects to Strava authorize URL with `scope=read,activity:read_all` and a signed `state`.
2. `GET /auth/strava/callback` verifies `state`, exchanges `code` for tokens, upserts athlete + encrypted tokens.
3. Enqueues a `backfill` job.
4. Optional `return_to` on step 1 (exact match against `OAUTH_RETURN_TO_ALLOWLIST`) is signed into
   `state`; the callback then sends the browser back there with a 303 (ADR 0015).

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

### 6b. New-activity notifications (Phase 5)
- After a live `activity create` event is upserted, webhook processing enqueues
  `notify_new_activity(strava_activity_id)` with job id `notify:{id}`. Backfill and incremental
  sync never do: history is not news.
- The job claims `(new_activity, id)` in `notifications` (`ON CONFLICT DO NOTHING`), commits, then
  sends through the `Notifier` (Telegram, or the `NullNotifier` without a token). A definite
  failure releases the claim and arq retries with backoff (10 s, 30 s, 90 s, 270 s; 5 tries).
  A timeout after the request went out keeps the claim: at most one message per activity.

### 7. Read API (API key in `X-API-Key` header)
- `GET /v1/activities?from=&to=&sport_type=&limit=&cursor=`: keyset pagination on `(start_date, id)`.
- `GET /v1/activities/{strava_activity_id}`: one activity; 404 if unknown or soft-deleted.
- `GET /v1/stats/weekly?from=&to=&sport_type=`: per ISO week distance, moving time, elevation, count
  (SQL aggregation).
- `GET /v1/stats/summary?from=&to=&sport_type=`: totals for the range, the same totals per
  `sport_type`, and the longest activity (greatest distance). One SQL query per block.
- `GET /v1/sync/status`: last sync runs, last webhook, webhook retry and dead-letter counts, current
  rate-limit usage, circuit state of every process (each publishes its breaker transitions to Redis).
- Responses include `last_synced_at`, so the client knows how fresh the data is when Strava is degraded.

### 7b. Training API (Phase 6, `/v1/training`, API key)
Routers in `api/training/`; every number (volume, e1RM, records, weekly muscle volume) comes from
`training/math.py`. Weights are exact decimals in requests (0–500 kg in 0.25 steps; reps 0–100;
RPE 1–10 in 0.5 steps) and JSON numbers in responses.
- Exercises: `GET /exercises?q=&muscle=&equipment=`; custom ones via `POST /exercises` and
  `PATCH /exercises/{id}` (built-ins are read-only, `409`).
- Programs: CRUD under `/programs`, `GET /programs/active`, `POST /programs/{id}/activate`
  (one active at a time).
- Workouts: `PUT /workouts/{client_id}` (idempotent start, free or `program_day_id`),
  `GET /workouts` (keyset on `(started_at, id)`, ADR 0009), `GET /workouts/{id}`,
  `POST /workouts/{id}/finish`, `DELETE`.
  Start, get and finish return one shape: summary (`volume_kg`, `set_count`), `planned` (the day's
  exercises with `last_performance`), `sets` and `records` (PRs the sets beat against all earlier
  workouts).
- Sets: `PUT /workouts/{id}/sets/{client_id}` upserts by a client-generated UUID (`201` first,
  `200` on a repeat, `409` when the id belongs to another workout); `DELETE` is idempotent (ADR 0017).
- Progress: `GET /exercises/{id}/progress` (best set, e1RM and volume per workout),
  `GET /volume/weekly` (working sets and kg per ISO week and primary muscle), `GET /prs` (standing
  records, found by replaying workouts oldest first through `detect_prs`).
- Body metrics: `PUT /body-metrics/{date}`, `GET /body-metrics?from=&to=`.
- Planning (ADR 0018, all pure functions in `training/`): `POST /programs/generate` returns a
  deterministic rule-based preview (`generator.py`), and its `program` field is the body to `POST
  /programs` to save it. Each `planned` exercise of a workout has a `suggestion` from double
  progression (`progression.py`: `start` / `increase` / `hold` / `deload`, with `weight_kg`).
  `GET /plates?target=` gives the plates per side (`plates.py`), using `GYM_BAR_KG` and
  `GYM_PLATES`.
- Next day (P6.8): `GET /programs/active/next-day` is the active program's day that is up, in
  rotation: the day after the one the latest workout followed (wrapping around), the first day
  without history, or the day of a still-open workout (`open_workout_id`). Planned exercises come
  with their `suggestion`, so `/today` in the bot shows suggested weights without starting a workout.

### 7c. Bot: training and nutrition commands (Phase 6, P6.8)
The bot stays an API client (read and write, same API key). Commands live in `Feature` groups
(`bot/training.py`, `bot/nutrition.py`, `bot/checkin.py`) that the dispatcher asks in turn:
- `/today` (next program day with suggested weights), `/plates 102.5`, `/log bench 80x5x3`
  (also `80x5,5,4` and `bw x12x3`, one parser in `bot/parsing.py` shared with the check-in),
  `/done` (finish, summary with volume and records), `/eat <food> <grams>`, `/kcal`, `/weight 78.4`.
- **Local day**: "today" is the owner's day in `CHECKIN_TZ` (default `Europe/Istanbul`), not UTC:
  `/log` adds to the open workout started on that day (or starts a free one), `/eat`, `/kcal` and
  `/weight` send that date explicitly. The meal is picked from the local hour.
- **Idempotency**: client ids are `uuid5` of `tg:{chat}:{update_id}:{n}` (`/log` set n) and
  `tg:{chat}:{update_id}:eat`. A redelivered update (the bot crashed before confirming it)
  rewrites the same rows; a set that already exists keeps its `set_index`.
- **Exercise names**: a small alias table (`bench`, `dl`, `ohp`, `rdl`, `pullup`, …), then
  `GET /exercises?q=` matched on slug/name, exact before prefix. Food names match stored foods
  (favourites first), falling back to the Open Food Facts lookup. More than one candidate → a
  numbered list; the choice waits in Redis (`bot:pending:{chat}`, 15 min) and a number answers it.
- **Wording**: training texts come from the tone packs; food, scale, sleep and energy texts come
  from a tone-free layer (`messages/neutral.py`, `NeutralKey`), identical in every `BOT_TONE`.

### 7d. Daily check-in (Phase 6, P6.9, ADR 0020)
- **API** (`/v1/checkins`, API key, local days): `GET ?from=&to=` (default 12 weeks),
  `GET /{date}`, `PUT /{date}` (upsert by date: `201` / `200`), `GET /summary?from=&to=` (current
  and longest streak, adherence = planned days done / planned days per ISO week from the active
  program's `days_per_week`, minus sick/injured days; done + partial count as done).
- **Scheduler**: worker cron every 5 minutes (`notify/checkin.py`). At or after `CHECKIN_TIME`
  local (`CHECKIN_TZ`, the wall time of each local date, DST-safe) it sends the prompt once, only
  if that day has no check-in; one reminder `CHECKIN_REMINDER_MINUTES` later, still unanswered.
  "Sent" is a claim in `notifications` (`checkin_prompt` / `checkin_reminder`, object id
  `yyyymmdd`), so restarts and overlapping ticks never send twice. Off without a bot token or a
  chat, or with `CHECKIN_ENABLED=false`.
- **Conversation** (`bot/checkin.py`, state diagram 17): a state machine in Redis
  (`checkin:{chat}:{yyyymmdd}`, 6 h TTL). Status buttons → planned exercises one by one (As
  planned = planned sets × bottom of the rep range at the suggested weight, ±2.5 kg, Skip, or
  typed sets) or free `/log` lines without a program → reason (skipped) → scale, sleep, energy
  (each skippable) → summary with volume, records and streak, plus an Edit button. Works without
  an Anthropic key.
- **Idempotency**: sets use `uuid5("checkin:{date}:{exercise_id}:{set_index}")`, the check-in is
  a `PUT` by date; buttons carry a per-step `seq` (stale or double presses are answered politely
  and change nothing); a redelivered text answer is recognised by its `update_id`.
- **Web**: `/training/checkins` calendar heatmap and day editor; streak and adherence tiles on
  the dashboard (writes through the BFF's CSRF-checked `PUT`).

### 8. Operations
- `GET /health/live` (process up), `GET /health/ready` (DB + Redis reachable).
- `GET /metrics` Prometheus endpoint on the API; each worker serves its own on
  `WORKER_METRICS_PORT` (default 9100). One registry per process, no multiprocess mode (ADR 0010).
- JSON logs with `request_id` (API) / `job_id`, `job_name`, `athlete_id` or `event_id` (worker)
  correlation.
- Public demo (P7.9, ADR 0028): `compose.demo.yml` runs the same image with `DEMO_MODE=true`.
  `DemoReadOnlyMiddleware` answers every non-GET request and `/auth/strava/*` with
  `403 This is a read-only demo.` (header `X-Trainsync-Demo: read-only`) before routing. The data
  is `trainsync.demo.seed` (synthetic, fixed RNG, twelve weeks before today), written by
  `python -m trainsync.demo reset` (wipe + seed in one transaction, DEMO_MODE only) on `up` and
  nightly by the demo worker (`trainsync.demo.worker`, reset cron only).

## Failure modes this design handles

| Failure | Behavior | Proven by (`make test-fault`) |
|---|---|---|
| Strava 5xx / timeouts | retries with backoff → circuit opens → jobs delayed, reads unaffected | [`tests/fault/test_strava_5xx_burst.py`](../tests/fault/test_strava_5xx_burst.py), [`tests/fault/test_strava_timeouts.py`](../tests/fault/test_strava_timeouts.py) |
| Rate limit near / exceeded | backfill pauses, webhooks still processed; 429 waits for window reset | [`tests/fault/test_rate_limit_burst.py`](../tests/fault/test_rate_limit_burst.py) |
| Worker crash mid-backfill | resumes from persisted cursor; upserts are idempotent | [`tests/fault/test_worker_restart.py`](../tests/fault/test_worker_restart.py) (real SIGKILL) |
| Duplicate webhook delivery | dedup key, `ON CONFLICT DO NOTHING` | [`tests/fault/test_duplicate_webhooks.py`](../tests/fault/test_duplicate_webhooks.py) |
| Out-of-order webhook events | worker always fetches the current activity state | [`tests/fault/test_out_of_order_webhooks.py`](../tests/fault/test_out_of_order_webhooks.py) |
| Missed webhooks | incremental sync with an overlap window | [`tests/fault/test_missed_webhooks.py`](../tests/fault/test_missed_webhooks.py) |
| Expired / rotated tokens | proactive refresh, 401 retry, per-athlete lock | [`tests/fault/test_token_rotation.py`](../tests/fault/test_token_rotation.py) |
| User revokes access | deauth event → tokens and data removed (also mid-backfill) | [`tests/fault/test_deauth_during_backfill.py`](../tests/fault/test_deauth_during_backfill.py) |
| Telegram down when a new activity arrives | notification claim released, job retried with backoff, exactly one message once Telegram is back | [`tests/fault/test_telegram_down.py`](../tests/fault/test_telegram_down.py) |
