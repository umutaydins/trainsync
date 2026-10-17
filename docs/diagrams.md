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
- [11. State — circuit breaker](#11-state--circuit-breaker)
- [12. State — webhook event](#12-state--webhook-event)
- [13. State — sync run](#13-state--sync-run)
- [14. Activity — rate-limit budget decision](#14-activity--rate-limit-budget-decision)

---

## 1. Component diagram

```mermaid
flowchart LR
    strava[("Strava API")]
    client_user(["API client<br/>(curl, notebooks)"])

    subgraph trainsync
        direction LR
        subgraph api["API process (FastAPI)"]
            auth["auth router<br/>/auth/strava/*"]
            hooks["webhooks router<br/>/webhooks/strava"]
            read["read API<br/>/v1/*"]
            ops["health + metrics"]
        end

        subgraph worker["Worker process (arq)"]
            backfill["backfill job"]
            incr["incremental_sync<br/>(cron 30 min)"]
            proc["process_webhook_event"]
            retry["retry_failed_webhooks<br/>(cron 5 min)"]
        end

        subgraph sc["strava package"]
            sclient["StravaClient"]
            tokens["TokenManager"]
            budget["RateBudget"]
            breaker["CircuitBreaker"]
        end

        pg[("PostgreSQL")]
        redis[("Redis<br/>queue · locks · budget")]
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
    sclient -- "HTTPS (httpx)" --> strava
    worker -- "upsert" --> pg
    read -- "SELECT" --> pg
```

## 2. Deployment diagram (docker compose)

```mermaid
flowchart TB
    browser(["Browser / curl<br/>on host"])

    subgraph host["Docker host"]
        subgraph net["compose network"]
            api["api<br/>uvicorn :8000"]
            worker["worker<br/>arq"]
            migrate["migrate<br/>alembic upgrade head<br/>(one-shot)"]
            fake["fake-strava<br/>uvicorn :8001"]
            pg[("postgres:16<br/>volume pgdata")]
            rd[("redis:7")]
        end
    end

    browser -- ":8000" --> api
    browser -- ":8001 (OAuth authorize)" --> fake
    migrate --> pg
    api --> pg
    api --> rd
    worker --> pg
    worker --> rd
    api -- "token exchange" --> fake
    worker -- "API calls" --> fake
    fake -. "webhook events" .-> api
```

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
```

## 4. Class diagram — core modules

```mermaid
classDiagram
    direction LR

    class Settings {
        +str database_url
        +str redis_url
        +str strava_api_base_url
        +str strava_oauth_base_url
        +SecretStr token_encryption_key
        +list~SecretStr~ api_keys
    }

    class StravaClient {
        -AsyncClient http
        -TokenProvider tokens
        -RetryPolicy policy
        -Clock clock
        -Sleep sleep
        -on_rate_limit(snapshot)
        +get_athlete(athlete_id, priority) StravaAthlete
        +list_activities(athlete_id, before, after, page, per_page, priority) list~StravaActivity~
        +get_activity(athlete_id, activity_id, priority) StravaActivity
        +exchange_code(code) TokenResponse
        +refresh(refresh_token) TokenResponse
    }

    class TokenProvider {
        <<interface>>
        +access_token(athlete_id) str
        +force_refresh(athlete_id) str
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
        +backoff(attempt) float
        +is_retryable(outcome) bool
    }

    class RateBudget {
        +float low_priority_threshold
        +record(snapshot)
        +allow(priority) Allowance
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

    class TokenCipher {
        +encrypt(plain) bytes
        +decrypt(cipher) str
    }

    class TokenRepository {
        +get(athlete_id) Tokens
        +upsert(athlete_id, access, refresh, expires_at, scope)
        +delete(athlete_id)
    }

    class ActivityRepository {
        +upsert_many(athlete_id, activities) int
        +soft_delete(strava_activity_id)
        +delete_for_athlete(athlete_id)
        +max_start_date(athlete_id) datetime
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
    class StravaUnavailable {
        <<exception>>
    }

    class SyncJobs {
        <<arq jobs>>
        +backfill(ctx, athlete_id)
        +incremental_sync(ctx, athlete_id)
        +process_webhook_event(ctx, event_id)
    }

    SyncJobs --> StravaClient
    SyncJobs --> ActivityRepository
    TokenProvider <|.. TokenManager
    StravaClient --> TokenProvider
    StravaClient --> RetryPolicy
    StravaClient --> RateBudget
    StravaClient --> CircuitBreaker
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

## 11. State — circuit breaker

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

## 12. State — webhook event

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

## 13. State — sync run

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

## 14. Activity — rate-limit budget decision

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
