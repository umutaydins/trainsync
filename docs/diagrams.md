# Diagrams

All diagrams are Mermaid, so GitHub renders them inline. They describe the design in
[architecture.md](architecture.md); keep them in sync when the code changes.

- [1. Component diagram](#1-component-diagram)
- [2. Deployment diagram (docker compose)](#2-deployment-diagram-docker-compose)
- [3. Data model (ER)](#3-data-model-er)
- [4. Class diagram — core modules](#4-class-diagram--core-modules)
- [5. Sequence — OAuth connect](#5-sequence--oauth-connect)
- [6. Sequence — token refresh with per-athlete lock](#6-sequence--token-refresh-with-per-athlete-lock)
- [7. Sequence — Strava call: retries, rate limit, breaker](#7-sequence--strava-call-retries-rate-limit-breaker)
- [8. Sequence — resumable backfill](#8-sequence--resumable-backfill)
- [9. Sequence — webhook ack-then-process](#9-sequence--webhook-ack-then-process)
- [10. Sequence — deauthorization](#10-sequence--deauthorization)
- [11. Sequence — dashboard request through the BFF](#11-sequence--dashboard-request-through-the-bff)
- [12. Sequence — new activity → notification](#12-sequence--new-activity--notification)
- [13. State — circuit breaker](#13-state--circuit-breaker)
- [14. State — webhook event](#14-state--webhook-event)
- [15. State — sync run](#15-state--sync-run)
- [16. Activity — rate-limit budget decision](#16-activity--rate-limit-budget-decision)

---

## 1. Component diagram

```mermaid
flowchart LR
    strava[("Strava API")]
    client_user(["API client<br/>(curl, notebooks)"])
    browser(["Browser"])
    tg_user(["Telegram chat"])
    telegram[("Telegram Bot API")]
    anthropic[("Anthropic API<br/>(optional)")]

    subgraph trainsync
        direction LR
        subgraph web["Web process (Next.js, web/)"]
            gate["proxy.ts<br/>session-cookie gate"]
            pages["server components<br/>dashboard · activities · sync"]
            bff["BFF route /api/ts/v1/*<br/>method + path allowlist, CSRF on writes"]
            upstream["lib/upstream.ts<br/>adds X-API-Key"]
        end

        subgraph bot["Bot process (python -m trainsync.bot)"]
            poller["Poller<br/>getUpdates long polling"]
            dispatch["Dispatcher<br/>chat allowlist"]
            cmds["Commands<br/>/week /last /stats /status"]
            assistant["Assistant<br/>Claude tool use (optional)"]
            readapi["ReadApi<br/>httpx → /v1/*"]
        end

        subgraph api["API process (FastAPI)"]
            auth["auth router<br/>/auth/strava/*"]
            hooks["webhooks router<br/>/webhooks/strava"]
            read["read API<br/>/v1/*"]
            ops["health + /metrics"]
        end

        subgraph worker["Worker process (arq)"]
            backfill["backfill job"]
            incr["incremental_sync"]
            proc["process_webhook_event"]
            sched["schedule_incremental<br/>(cron :00, :30)"]
            retry["retry_webhooks<br/>(cron 5 min)"]
            notify["notify_new_activity"]
            notifier["Notifier<br/>TelegramNotifier · NullNotifier"]
        end

        subgraph sc["strava package"]
            sclient["StravaClient"]
            tokens["TokenManager"]
            budget["RateBudget"]
            breaker["CircuitBreaker"]
        end

        pg[("PostgreSQL")]
        redis[("Redis<br/>queue · locks · budget · breaker state")]
    end

    strava -- "webhook POST" --> hooks
    client_user -- "X-API-Key" --> read
    hooks -- "insert (dedup)" --> pg
    hooks -- "enqueue" --> redis
    redis -- "jobs" --> worker
    worker --> sclient
    auth --> sclient
    sclient --> tokens
    sclient --> budget
    sclient --> breaker
    tokens -- "lock" --> redis
    budget -- "usage" --> redis
    breaker -- "state" --> redis
    read -- "status: budget, breakers" --> redis
    sclient -- "HTTPS (httpx)" --> strava
    worker -- "upsert" --> pg
    read -- "SELECT" --> pg

    browser -- "session cookie" --> gate
    gate --> pages
    gate --> bff
    pages --> upstream
    bff --> upstream
    upstream -- "X-API-Key" --> read

    tg_user -. "messages" .-> telegram
    poller -- "getUpdates" --> telegram
    poller --> dispatch
    dispatch --> cmds
    dispatch -- "plain text" --> assistant
    assistant -- "plan tool calls" --> anthropic
    assistant -- "rate limit per chat" --> redis
    cmds --> readapi
    assistant --> readapi
    readapi -- "X-API-Key" --> read
    dispatch -- "sendMessage" --> telegram

    proc -- "enqueue (activity create only)" --> redis
    notify -- "claim (kind, object_id)" --> pg
    notify --> notifier
    notifier -- "sendMessage" --> telegram
```

The web app and the bot are clients of the read API: neither touches PostgreSQL, and the API key
stays server-side (ADRs 0011, 0012). New-activity notifications run in the worker with its own
Telegram client, so they do not depend on the bot process.

## 2. Deployment diagram (docker compose)

```mermaid
flowchart TB
    browser(["Browser / curl<br/>on host"])
    telegram[("api.telegram.org<br/>(only with TELEGRAM_BOT_TOKEN)")]
    anthropic[("Anthropic API<br/>(only with ANTHROPIC_API_KEY)")]

    subgraph host["Docker host"]
        subgraph net["compose network"]
            web["web<br/>Next.js standalone :3000"]
            api["api<br/>uvicorn :8000"]
            worker["worker<br/>arq · metrics :9100"]
            bot["bot<br/>python -m trainsync.bot<br/>metrics :9101"]
            migrate["migrate<br/>alembic upgrade head<br/>(one-shot)"]
            fake["fake-strava<br/>uvicorn :8001"]
            pg[("postgres:16<br/>volume pgdata")]
            rd[("redis:7<br/>volume redisdata")]
        end
    end

    browser -- ":3000 (dashboard)" --> web
    browser -- ":8000" --> api
    browser -- ":9100 (metrics)" --> worker
    browser -- ":9101 (metrics)" --> bot
    browser -- ":8001 (OAuth authorize)" --> fake
    web -- "http://api:8000 + X-API-Key" --> api
    bot -- "http://api:8000 + X-API-Key" --> api
    migrate --> pg
    api --> pg
    api --> rd
    worker --> pg
    worker --> rd
    bot -- "assistant rate limit" --> rd
    api -- "token exchange" --> fake
    worker -- "API calls" --> fake
    fake -. "webhook events" .-> api
    bot -- "getUpdates / sendMessage" --> telegram
    worker -- "notifications" --> telegram
    bot -. "questions" .-> anthropic
```

Without `TELEGRAM_BOT_TOKEN` the bot does not poll (it only serves its metrics and stays healthy)
and the worker uses the `NullNotifier`, so the stack and `make compose-smoke` behave the same with
or without a token.

## 3. Data model (ER)

```mermaid
erDiagram
    athletes ||--o| oauth_tokens : "has"
    athletes ||--o{ activities : "owns"
    athletes ||--o{ sync_runs : "has"

    athletes {
        bigint id PK
        bigint strava_athlete_id UK
        boolean active
        timestamptz created_at
    }
    oauth_tokens {
        bigint athlete_id PK, FK
        bytea access_token_enc
        bytea refresh_token_enc
        timestamptz expires_at
        text scope
    }
    activities {
        bigint id PK
        bigint strava_activity_id UK
        bigint athlete_id FK
        text name
        text sport_type
        timestamptz start_date
        float distance_m
        int moving_time_s
        int elapsed_time_s
        float elevation_gain_m
        float average_heartrate "nullable"
        jsonb raw
        timestamptz deleted_at "nullable, soft delete"
        timestamptz synced_at
    }
    sync_runs {
        bigint id PK
        bigint athlete_id FK
        text kind "backfill | incremental"
        text status "running | paused | succeeded | failed"
        jsonb cursor
        int pages
        int upserted
        text error
        timestamptz started_at
        timestamptz updated_at "heartbeat"
        timestamptz finished_at
    }
    webhook_events {
        bigint id PK
        text dedup_key UK
        jsonb payload
        text status "pending | processing | processed | failed"
        int attempts
        timestamptz received_at
        timestamptz last_attempt_at
        timestamptz processed_at
    }
    notifications {
        bigint id PK
        text kind "new_activity"
        bigint object_id "strava_activity_id, UK with kind"
        timestamptz sent_at
    }

    foods ||--o{ food_logs : "logged as"
    foods {
        bigint id PK
        text name
        text brand "nullable"
        varchar barcode UK "nullable"
        numeric kcal_100g
        numeric protein_100g "nullable = unknown"
        numeric carbs_100g "nullable = unknown"
        numeric fat_100g "nullable = unknown"
        text source "manual | openfoodfacts"
        boolean favorite
        timestamptz created_at
    }
    food_logs {
        bigint id PK
        uuid client_id UK "idempotent PUT"
        date date
        text meal "breakfast | lunch | dinner | snack"
        bigint food_id FK
        numeric grams
        timestamptz created_at
    }
    nutrition_profile {
        int id PK "always 1"
        text sex
        int birth_year
        numeric height_cm
        text activity_baseline "sedentary | light | moderate"
        int kcal_target "nullable"
        int protein_target_g "nullable"
        timestamptz updated_at
    }
```

Nutrition (P6.4, ADR 0019) is single-user: no `athlete_id`. Body weight for the BMR estimate comes
from `body_metrics` (training), exercise energy from `activities.raw`.

`notifications` has no foreign key: a row is the idempotency claim for one message (ADR 0012),
kept even if the activity is deleted later.

### Training (Phase 6)

Single user, so no `athlete_id`. `workouts.strava_activity_id` is a link, not a foreign key.

```mermaid
erDiagram
    programs ||--o{ program_days : "has"
    program_days ||--o{ program_exercises : "plans"
    exercises ||--o{ program_exercises : "used in"
    program_days |o--o{ workouts : "followed by"
    workouts ||--o{ workout_sets : "logs"
    exercises ||--o{ workout_sets : "of"

    exercises {
        int id PK
        text slug UK
        text name
        text primary_muscle
        text_array secondary_muscles
        text equipment
        text movement_pattern "nullable"
        boolean is_custom
        timestamptz created_at
    }
    programs {
        bigint id PK
        text name
        text goal "strength | hypertrophy | general"
        int days_per_week
        int weeks
        boolean active "at most one true"
        timestamptz created_at
    }
    program_days {
        bigint id PK
        bigint program_id FK
        int day_index "UK with program_id"
        text name
    }
    program_exercises {
        bigint id PK
        bigint program_day_id FK
        int exercise_id FK
        int position
        int sets
        int rep_min
        int rep_max
        int rest_seconds
        numeric start_weight_kg "nullable"
        text progression "double | none"
    }
    workouts {
        bigint id PK
        bigint program_day_id FK "nullable"
        timestamptz started_at
        timestamptz ended_at "nullable"
        text notes
        bigint strava_activity_id "nullable, no FK"
    }
    workout_sets {
        bigint id PK
        uuid client_id UK "client-generated"
        bigint workout_id FK
        int exercise_id FK
        int set_index
        int reps
        numeric weight_kg
        numeric rpe "nullable"
        boolean is_warmup
        timestamptz completed_at
        int rest_seconds "nullable, actual rest"
    }
    body_metrics {
        date date PK
        numeric weight_kg
    }
```

## 4. Class diagram — core modules

Generated from the code (public methods; Protocols shown as interfaces).

```mermaid
classDiagram
    direction LR

    class Settings {
        +str database_url
        +str redis_url
        +str strava_api_base_url
        +str strava_oauth_base_url
        +int|None strava_webhook_subscription_id
        +int strava_breaker_failure_threshold
        +float strava_breaker_cooldown_s
        +int worker_metrics_port
        +SecretStr token_encryption_key
        +list~SecretStr~ api_keys
        +list~str~ oauth_return_to_allowlist
        +SecretStr telegram_bot_token
        +list~int~ telegram_allowed_chat_ids
        +int|None telegram_notify_chat_id
        +str dashboard_public_url
        +SecretStr anthropic_api_key
        +str assistant_model
        +notify_chat_id() int|None
    }

    class StravaClient {
        -AsyncClient http
        -TokenProvider tokens
        -RetryPolicy policy
        -RateLimitHook budget
        -CircuitBreaker breaker
        -Clock clock
        -Sleep sleep
        +breaker_state BreakerState
        +get_athlete(athlete_id, priority) StravaAthlete
        +list_activities(athlete_id, before, after, page, per_page, priority) list~StravaActivity~
        +get_activity(athlete_id, activity_id, priority) StravaActivity
        +exchange_code(code) TokenResponse
        +refresh(refresh_token) TokenResponse
        +with_token_provider(provider) StravaClient
    }

    class TokenProvider {
        <<interface>>
        +access_token(athlete_id) str
        +force_refresh(athlete_id) str
    }

    class RateLimitHook {
        <<interface>>
        +allow(priority) Allowance
        +record(snapshot)
        +block_until(reset_at)
    }

    class TokenManager {
        -TokenStore store
        -RefreshLock lock
        -TokenRefresher refresher
        -Clock clock
        +access_token(athlete_id) str
        +force_refresh(athlete_id) str
    }

    class RedisRefreshLock {
        +acquire(athlete_id) str
        +release(athlete_id, owner)
        +is_held(athlete_id) bool
    }

    class SqlTokenStore {
        +get(athlete_id) Tokens
        +save(athlete_id, tokens)
    }

    class RetryPolicy {
        +int max_attempts
        +float base
        +float cap
        +ceiling(attempt) float
        +backoff(attempt, rng) float
    }

    class RateBudget {
        +float low_priority_threshold
        +record(snapshot)
        +allow(priority) Allowance
        +block_until(reset_at)
        +latest() BudgetState
    }

    class CircuitBreaker {
        +int failure_threshold
        +timedelta cooldown
        +state BreakerState
        +guard() async context
        +before_call() bool
        +on_success(probe)
        +on_failure(probe)
    }

    class RedisBreakerPublisher {
        <<BreakerListener>>
        +__call__(state, retry_at)
    }

    class TokenCipher {
        +from_settings(settings) TokenCipher
        +encrypt(plain) bytes
        +decrypt(cipher) str
    }

    class TokenRepository {
        +get(athlete_id) Tokens
        +upsert(athlete_id, access, refresh, expires_at, scope)
        +delete(athlete_id)
    }

    class AthleteRepository {
        +upsert_connected(strava_athlete_id) int
        +by_strava_id(strava_athlete_id) Athlete
        +is_active_locked(athlete_id) bool
        +deauthorize(athlete_id) int
    }

    class ActivityRepository {
        +upsert_many(athlete_id, activities) int
        +soft_delete(strava_activity_id) bool
        +delete_for_athlete(athlete_id) int
        +max_start_date(athlete_id) datetime
    }

    class SyncRunRepository {
        +open_run(athlete_id, kind, lock) SyncRun
        +create(athlete_id, kind, cursor, now) SyncRun
        +checkpoint(run_id, cursor, upserted, now)
        +set_status(run_id, status, now, error)
        +has_succeeded(athlete_id, kind) bool
    }

    class WebhookEventRepository {
        +insert_new(dedup_key, payload) int
        +claim(event_id, now) WebhookEvent
        +set_status(event_id, status, processed_at)
        +retry_candidates(now, stale_after, limit) list~WebhookEvent~
        +release_stuck(event_id, claimed_at) bool
        +count_dead() int
    }

    class ReadRepository {
        +active_athlete_ids(athlete_id) list~int~
        +activity_page(filter, after, limit) page
        +activity(strava_activity_id, athlete_ids) Activity
        +weekly_stats(filter, first_week, last_week) list~WeekStats~
        +summary(filter) Summary
        +latest_runs(athlete_ids) dict
        +webhook_summary() WebhookSummary
        +last_synced_at(athlete_ids) datetime
    }

    class StravaError {
        <<exception>>
    }
    class RateLimited {
        <<exception>>
        +datetime reset_at
    }
    class CircuitOpen {
        <<exception>>
        +datetime retry_at
    }
    class StravaAuthError {
        <<exception>>
    }
    class StravaUnauthorized {
        <<exception>>
    }
    class StravaNotFound {
        <<exception>>
    }
    class StravaRequestError {
        <<exception>>
        +int status_code
    }
    class StravaUnavailable {
        <<exception>>
    }

    class SyncDeps {
        +sessionmaker
        +ActivitySource strava
        +Budget budget
        +Clock clock
    }

    class WebhookDeps {
        +sessionmaker
        +ActivityFetcher strava
        +Clock clock
        +on_new_activity(strava_activity_id) callback|None
    }

    class Notifier {
        <<interface>>
        +str channel
        +send(chat_ref, text)
    }

    class TelegramNotifier {
        +str channel = telegram
        -TelegramApi api
        +send(chat_ref, text)
    }

    class NullNotifier {
        +str channel = null
        +send(chat_ref, text)
    }

    class TelegramApi {
        -AsyncClient http
        -SecretStr token
        -Sleep sleep
        +get_updates(offset, poll_timeout) list~Update~
        +send_message(chat_id, text)
    }

    class NotifyDeps {
        +sessionmaker
        +Notifier notifier
        +str|None chat_ref
        +str dashboard_url
        +Clock clock
    }

    class NotificationRepository {
        +claim(kind, object_id, now) bool
        +release(kind, object_id)
    }

    class NotifyFailedError {
        <<exception>>
        +float|None retry_after
    }
    class DeliveryUnknownError {
        <<exception>>
    }

    class WorkerJobs {
        <<arq jobs>>
        +backfill(ctx, athlete_id)
        +incremental_sync(ctx, athlete_id)
        +process_webhook_event(ctx, event_id)
        +schedule_incremental(ctx) cron 0,30
        +retry_webhooks(ctx) cron every 5 min
        +notify_new_activity(ctx, strava_activity_id) max 5 tries
    }

    WorkerJobs --> SyncDeps
    WorkerJobs --> WebhookDeps
    SyncDeps --> StravaClient
    SyncDeps --> RateBudget
    WebhookDeps --> StravaClient
    WorkerJobs ..> SyncRunRepository
    WorkerJobs ..> ActivityRepository
    WorkerJobs ..> AthleteRepository
    WorkerJobs ..> WebhookEventRepository
    WorkerJobs --> NotifyDeps
    NotifyDeps --> Notifier
    WorkerJobs ..> NotificationRepository
    Notifier <|.. TelegramNotifier
    Notifier <|.. NullNotifier
    TelegramNotifier --> TelegramApi
    TelegramNotifier ..> NotifyFailedError : raises
    TelegramNotifier ..> DeliveryUnknownError : raises
    TokenProvider <|.. TokenManager
    RateLimitHook <|.. RateBudget
    StravaClient --> TokenProvider
    StravaClient --> RetryPolicy
    StravaClient --> RateLimitHook
    StravaClient --> CircuitBreaker
    CircuitBreaker --> RedisBreakerPublisher : listener
    StravaClient ..> Settings
    TokenManager --> SqlTokenStore
    TokenManager --> RedisRefreshLock
    TokenManager ..> StravaClient : refresh()
    SqlTokenStore --> TokenRepository
    TokenRepository --> TokenCipher
    StravaError <|-- RateLimited
    StravaError <|-- CircuitOpen
    StravaError <|-- StravaAuthError
    StravaAuthError <|-- StravaUnauthorized
    StravaError <|-- StravaNotFound
    StravaError <|-- StravaRequestError
    StravaError <|-- StravaUnavailable
    StravaClient ..> StravaError : raises
```

## 5. Sequence — OAuth connect

```mermaid
sequenceDiagram
    autonumber
    actor U as User (browser)
    participant API as trainsync API
    participant S as Strava OAuth
    participant DB as PostgreSQL
    participant Q as Redis (arq)

    U->>API: GET /auth/strava/login
    API->>API: sign_state(now)
    API-->>U: 302 → /oauth/authorize?client_id&scope=read,activity:read_all&state
    U->>S: authorize
    S-->>U: 302 → /auth/strava/callback?code&state&scope
    U->>API: GET /auth/strava/callback
    API->>API: verify_state(), check scope contains activity:read_all
    alt invalid state / missing scope / access_denied
        API-->>U: 400
    else ok
        API->>S: POST /oauth/token (authorization_code)
        S-->>API: access_token, refresh_token, expires_at, athlete
        API->>DB: BEGIN, upsert athlete (active=true), upsert encrypted tokens, COMMIT
        API->>Q: enqueue backfill (job id backfill:{athlete_id})
        API-->>U: 200 {athlete_id, backfill: "queued"}
    end
```

## 6. Sequence — token refresh with per-athlete lock

Two jobs need a token for the same athlete at the same moment, and the token is about to expire.

```mermaid
sequenceDiagram
    autonumber
    participant J1 as Job A
    participant J2 as Job B
    participant TM as TokenManager
    participant R as Redis
    participant DB as PostgreSQL
    participant S as Strava OAuth

    par
        J1->>TM: access_token(42)
    and
        J2->>TM: access_token(42)
    end
    TM->>DB: read tokens (expires in < 5 min)
    TM->>R: SET token-refresh:42 uuidA NX PX 15000
    R-->>TM: OK (A holds lock)
    TM->>R: SET token-refresh:42 uuidB NX PX 15000
    R-->>TM: nil (B waits)
    TM->>DB: re-read tokens (still expiring)
    TM->>S: POST /oauth/token (refresh_token)
    S-->>TM: new access + NEW refresh token
    TM->>DB: upsert encrypted tokens
    TM->>R: compare-and-delete token-refresh:42 uuidA
    TM-->>J1: new access token
    loop until lock free (bounded)
        TM->>R: lock still held?
    end
    TM->>DB: re-read tokens (now fresh)
    TM-->>J2: new access token (no second refresh)
```

## 7. Sequence — Strava call: retries, rate limit, breaker

```mermaid
sequenceDiagram
    autonumber
    participant Job
    participant C as StravaClient
    participant B as CircuitBreaker
    participant RB as RateBudget
    participant S as Strava API

    Job->>C: list_activities(before, priority=low)
    C->>RB: allow(low)
    alt usage ≥ 80%
        RB-->>C: denied, resume_at = next quarter hour
        C-->>Job: RateLimited → run paused, deferred
    else allowed
        C->>B: before_call()
        alt open, or half-open with a probe in flight
            B-->>C: CircuitOpen(retry_at)
            C-->>Job: CircuitOpen → run paused, job deferred to retry_at (+ jitter)
        else closed / half-open probe
            loop attempt 1..4
                C->>S: GET /athlete/activities (timeouts 3s/10s)
                S-->>C: response + X-RateLimit-* headers
                C->>RB: record(snapshot)
                alt 2xx
                    C->>B: on_success()
                    C-->>Job: activities
                else 429
                    C->>B: on_success() (Strava answered)
                    C-->>Job: RateLimited(reset_at) — no retry
                else 5xx / timeout
                    C->>C: sleep(full jitter backoff)
                else other 4xx
                    C->>B: on_success() (Strava answered)
                    C-->>Job: error — no retry
                end
            end
            C->>B: on_failure() (retries exhausted)
            C-->>Job: StravaUnavailable → run paused, deferred 30 s
        end
    end
```

## 8. Sequence — resumable backfill

```mermaid
sequenceDiagram
    autonumber
    participant W as Worker: backfill(42)
    participant DB as PostgreSQL
    participant C as StravaClient

    W->>DB: SELECT … FOR UPDATE open sync_run (backfill, running|paused)
    alt running and heartbeat (updated_at) < 5 min old
        W-->>W: already_running → return (another worker owns it)
    else none
        W->>DB: create {cursor.before = null}, status = running
    else paused, or running with a stale heartbeat (its worker died)
        W->>DB: status = running (keep cursor)
    end
    loop until history done
        W->>C: list_activities(before=cursor, page=1, per_page=200)
        C-->>W: page (≤ 200, newest first)
        alt page empty
            W->>DB: sync_run.status = succeeded
        else
            W->>DB: BEGIN
            W->>DB: INSERT … ON CONFLICT (strava_activity_id) DO UPDATE
            W->>DB: sync_run.cursor = min(start_date)+1, pages++, upserted += n, updated_at = now
            W->>DB: COMMIT
            opt short page that made no progress
                W->>DB: sync_run.status = succeeded
            end
        end
    end
    Note over W,DB: RateLimited / CircuitOpen / StravaUnavailable / budget denial → status = paused, job deferred.<br/>Crash anywhere → the next run starts from the last committed cursor.<br/>Re-fetching one page is harmless because upserts are idempotent.
```

## 9. Sequence — webhook ack-then-process

```mermaid
sequenceDiagram
    autonumber
    participant S as Strava
    participant API as POST /webhooks/strava
    participant DB as PostgreSQL
    participant Q as Redis (arq)
    participant W as Worker
    participant C as StravaClient

    S->>API: event {object_type, object_id, aspect_type, event_time, …}
    API->>API: validate, dedup_key = sha256(sub:type:id:aspect:time)
    API->>DB: INSERT webhook_events ON CONFLICT (dedup_key) DO NOTHING RETURNING id
    alt new row
        API->>Q: enqueue process_webhook_event(id), job id webhook:{id}
        Note over API,Q: enqueue fails → still 200; retry cron recovers stale pending
    else duplicate
        Note over API: nothing to enqueue
    end
    API-->>S: 200 (measured p99 ≈ 7 ms locally, hard limit 2 s)

    Q->>W: process_webhook_event(id)
    W->>DB: claim: status pending|failed → processing, attempts++, last_attempt_at = now
    alt unknown owner / inactive athlete
        Note over W: nothing to do
    else activity create / update
        W->>C: get_activity(object_id, priority=high)
        C-->>W: current state (or 404 → treat as deleted)
        W->>DB: athlete active FOR SHARE? → upsert (or soft delete)
    else activity delete
        W->>DB: soft delete
    end
    alt done
        W->>DB: status = processed
    else RateLimited / CircuitOpen
        W->>DB: status = pending, job deferred (arq Retry)
    else other error
        W->>DB: status = failed (retry cron: backoff 2^n min, 8 attempts)
    end
```

## 10. Sequence — deauthorization

```mermaid
sequenceDiagram
    autonumber
    participant S as Strava
    participant API as Webhook handler
    participant W as Worker
    participant DB as PostgreSQL

    S->>API: athlete update {authorized: "false"}
    API->>DB: insert event (dedup)
    API-->>S: 200
    API->>W: enqueue process_webhook_event
    W->>DB: BEGIN
    W->>DB: athletes.active = false (row lock: in-flight sync pages wait, then write nothing)
    W->>DB: DELETE oauth_tokens WHERE athlete_id
    W->>DB: DELETE activities WHERE athlete_id
    W->>DB: COMMIT, event processed
    Note over W,DB: Later events for this athlete are marked processed without fetching.
```

## 11. Sequence — dashboard request through the BFF

The browser only ever talks to the web server. The API key lives in the web server's environment
and is added in one place, `lib/upstream.ts` (ADR 0011).

```mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant P as proxy.ts (access gate)
    participant RSC as Dashboard page (server components)
    participant BFF as BFF route /api/ts/[...path]
    participant UP as lib/upstream.ts
    participant API as trainsync API /v1

    U->>P: GET /?from=2025-03-01&to=2025-12-31 (session cookie)
    P->>P: verifySessionToken(cookie, DASHBOARD_SESSION_SECRET)
    alt no or invalid session
        P-->>U: 307 → /login?next=… (a page) or 401 JSON (an /api/ call)
    else valid
        P->>RSC: render
        par one Suspense block each
            RSC->>UP: api.summary(from, to, sport)
            UP->>API: GET /v1/stats/summary + X-API-Key (timeout 10 s, no-store)
            API-->>UP: totals, by sport, last_synced_at
        and
            RSC->>UP: api.weekly(from, to, sport)
            UP->>API: GET /v1/stats/weekly + X-API-Key
            API-->>UP: weeks (zero-filled)
        end
        RSC-->>U: streamed HTML: KPI tiles, weekly chart, by sport (no key in it)
    end

    Note over U,BFF: Client components ("Load more" on /activities, the 15 s refresh on /sync)
    U->>P: GET /api/ts/v1/activities?cursor=… (session cookie)
    P->>BFF: valid session
    BFF->>BFF: allowedMethods(path)? (unknown path 404, wrong method 405)
    BFF->>UP: upstreamRequest(GET, path, query)
    UP->>API: GET /v1/activities?cursor=… + X-API-Key
    alt 2xx
        API-->>UP: page
        UP-->>BFF: data
        BFF-->>U: 200 JSON (Cache-Control: no-store)
    else API error / unreachable
        UP-->>BFF: status + short message (no upstream details, unreachable = 502)
        BFF-->>U: {error} with that status
    end

    Note over U,BFF: Writes (lib/mutate.ts): training, nutrition, check-ins
    U->>P: PUT /api/ts/v1/training/workouts/42/sets/<uuid> (session + ts_csrf cookies, X-CSRF-Token, JSON)
    P->>BFF: valid session (proxy.ts sets ts_csrf if it is missing)
    BFF->>BFF: allowlist (404/405) → Origin/Referer = WEB_PUBLIC_URL (403) → X-CSRF-Token = ts_csrf cookie (403)
    BFF->>BFF: application/json (415), ≤ 64 KB read with a cap (413), parses as JSON (400)
    BFF->>UP: upstreamRequest(PUT, path, query, body)
    UP->>API: PUT /v1/training/... + X-API-Key (no browser cookies or headers)
    API-->>UP: status + JSON
    UP-->>BFF: data, or {error, detail}
    BFF-->>U: same status, JSON only (no upstream headers)
```

## 12. Sequence — new activity → notification

Only a live `activity create` webhook leads to a notification; backfill and incremental sync
import history and never enqueue one. Exactly one message per activity (ADR 0012).

```mermaid
sequenceDiagram
    autonumber
    participant S as Strava
    participant API as POST /webhooks/strava
    participant DB as PostgreSQL
    participant Q as Redis (arq)
    participant W as Worker: process_webhook_event
    participant N as Worker: notify_new_activity
    participant T as Notifier (TelegramNotifier)

    S->>API: activity create (delivered twice)
    API->>DB: INSERT webhook_events ON CONFLICT (dedup_key) DO NOTHING
    Note over API,DB: the second delivery is a duplicate: nothing enqueued
    API->>Q: enqueue process_webhook_event(id)
    Q->>W: run
    W->>DB: claim event, fetch current state from Strava, upsert activity
    W->>Q: enqueue notify_new_activity(strava_id), job id notify:{strava_id}
    Note over W,Q: same job id already queued or recently done → not enqueued again
    Q->>N: run (try n)
    alt no chat configured (NullNotifier)
        N-->>N: disabled
    else activity deleted or athlete gone
        N-->>N: skipped
    else
        N->>DB: INSERT notifications (new_activity, strava_id) ON CONFLICT DO NOTHING, COMMIT
        alt already claimed
            N-->>N: duplicate: send nothing
        else claimed
            N->>T: send(chat_ref, text with link to /activities/{id})
            alt delivered
                T-->>N: ok → sent
            else no answer after the request went out (DeliveryUnknownError)
                T-->>N: keep the claim → unknown (better one missed message than two)
            else definite failure (NotifyFailedError, e.g. Telegram 5xx or 429)
                T-->>N: error
                N->>DB: DELETE the claim (release)
                N->>Q: arq Retry, defer max(10 s · 3^(n-1), retry_after), gave_up after 5 tries
            end
        end
    end
```

## 13. State — circuit breaker

```mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Closed : success, 4xx or 429 / reset failure count
    Closed --> Open : N consecutive StravaUnavailable (5xx / timeouts after retries)
    Open --> HalfOpen : cooldown elapsed
    Open --> Open : call → CircuitOpen(retry_at)
    HalfOpen --> Closed : probe answered (2xx, 4xx or 429)
    HalfOpen --> Open : probe fails
    HalfOpen --> HalfOpen : other calls → CircuitOpen (only one probe)
    HalfOpen --> HalfOpen : probe cancelled / non-Strava error → next call probes
```

Per process (ADR 0005). Defaults: N = 5, cooldown = 30 s.

## 14. State — webhook event

```mermaid
stateDiagram-v2
    [*] --> pending : POST stored (new dedup_key)
    pending --> processing : worker claims (attempts + 1)
    processing --> processed : applied / ignored (unknown owner, inactive athlete)
    processing --> pending : RateLimited / CircuitOpen (deferred) / worker shutdown
    processing --> failed : error
    failed --> processing : retry cron (backoff, attempts < 8)
    failed --> [*] : attempts ≥ 8 (dead letter)
    processed --> [*]
```

## 15. State — sync run

```mermaid
stateDiagram-v2
    [*] --> running : job starts
    running --> paused : budget denial / 429 / CircuitOpen / StravaUnavailable / worker shutdown
    paused --> running : deferred job resumes from cursor
    running --> running : heartbeat stale > 5 min (worker died) → next job takes over, same cursor
    running --> succeeded : history done (empty page, or short page with no progress)
    running --> failed : auth error / unexpected error
    succeeded --> [*]
    failed --> [*]
```

## 16. Activity — rate-limit budget decision

```mermaid
flowchart TD
    start([Strava call requested]) --> blocked{"blocked_until<br/>in the future?<br/>(after a 429)"}
    blocked -- yes --> wait["deny: resume at blocked_until"]
    blocked -- no --> snap{"snapshot from<br/>current 15-min window?"}
    snap -- no --> allow["allow"]
    snap -- yes --> prio{priority}
    prio -- high --> exhausted{"15-min usage<br/>= 100%?"}
    exhausted -- yes --> wait2["deny: resume at next quarter hour"]
    exhausted -- no --> allow
    prio -- low --> thr{"short or daily<br/>usage ≥ 80%?"}
    thr -- yes --> pause["deny: pause backfill/incremental<br/>until next window"]
    thr -- no --> allow
    allow --> doCall["call Strava, record X-RateLimit-* headers"]
    doCall --> is429{"429?"}
    is429 -- yes --> setblk["set blocked_until = next quarter hour"]
    is429 -- no --> done([done])
    setblk --> done
```
