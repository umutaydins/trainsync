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
- [17. State — daily check-in conversation](#17-state--daily-check-in-conversation)
- [18. Sequence — evening check-in prompt](#18-sequence--evening-check-in-prompt)
- [19. Sequence — log a set with retry](#19-sequence--log-a-set-with-retry)
- [20. Sequence — rest timer and a backgrounded tab](#20-sequence--rest-timer-and-a-backgrounded-tab)
- [21. Deployment — production on the MacBook (Phase 7)](#21-deployment--production-on-the-macbook-phase-7)
- [22. Sequence — nightly backup and weekly restore check](#22-sequence--nightly-backup-and-weekly-restore-check-p74-adr-0024)
- [23. Activity — make deploy and make rollback](#23-activity--make-deploy-and-make-rollback-p75-adr-0026)
- [24. State — uptime and stack alerts](#24-state--uptime-and-stack-alerts-p78-adr-0027)
- [25. Deployment — public read-only demo](#25-deployment--public-read-only-demo-p79-adr-0028)
- [26. Sequence — the coach during a workout](#26-sequence--the-coach-during-a-workout-p611-adr-0030)
- [27. Sequence — /lang and the chat's language](#27-sequence--lang-and-the-chats-language-p612-adr-0031)
- [28. Activity — a chat message in savage mode](#28-activity--a-chat-message-in-savage-mode-profanity-and-the-guardrails-p613-adr-0032)
- [29. Layers — code layout and allowed imports](#29-layers--code-layout-and-allowed-imports-adr-0033)
- [30. Sequence — sign-up with an invite, then login through the BFF](#30-sequence--sign-up-with-an-invite-then-login-through-the-bff-p81-p87-adr-0034)
- [31. Sequence — linking a Telegram chat with /link](#31-sequence--linking-a-telegram-chat-with-link-p84-adr-0036)
- [32. Sequence — progress summary with the versioned cache](#32-sequence--progress-summary-with-the-versioned-cache-p810-adr-0038)
- [33. Sequence — Monday progress digest](#33-sequence--monday-progress-digest-p811-adr-0038)

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
            gate["proxy.ts<br/>session-cookie gate → /login"]
            authh["route handlers<br/>/api/auth/* · /api/account · /api/strava/connect<br/>login, register, reset, delete"]
            pages["server components<br/>dashboard · activities · sync<br/>training · nutrition (PWA)"]
            bff["BFF route /api/ts/v1/*<br/>method + path allowlist, CSRF on writes"]
            upstream["lib/upstream.ts<br/>unseals the cookie, adds Bearer token"]
        end

        subgraph bot["Bot process (python -m trainsync.entrypoints.bot)"]
            poller["Poller<br/>getUpdates long polling"]
            dispatch["Dispatcher<br/>linked chats · /link /unlink<br/>unknown chat → hint"]
            links["ChatLinks<br/>chat → user cache (BOT_CHAT_CACHE_S)"]
            cmds["Commands<br/>/week /last /stats /status"]
            assistant["Assistant<br/>Claude tool use (optional)"]
            readapi["ReadApi<br/>httpx → /v1/*<br/>service key + X-Acting-User"]
        end

        subgraph api["API process (FastAPI)"]
            auth["strava router<br/>/auth/strava/* · /v1/me/strava"]
            accounts["accounts<br/>/v1/auth/* · /v1/me · /v1/admin/*<br/>/v1/me/telegram · /v1/telegram/chats"]
            principal["CurrentUser<br/>Bearer · API key · service key + X-Acting-User"]
            hooks["webhooks router<br/>/webhooks/strava"]
            read["read API<br/>/v1/* · /v1/stats progress (ADR 0038)"]
            ops["health + /metrics"]
        end

        subgraph worker["Worker process (arq)"]
            backfill["backfill job"]
            incr["incremental_sync"]
            proc["process_webhook_event"]
            sched["schedule_incremental<br/>(cron :00, :30)"]
            retry["retry_webhooks<br/>(cron 5 min)"]
            notify["notify_new_activity"]
            purge["purge_user"]
            digest["digest_tick<br/>(cron 5 min)"]
            notifier["Notifier<br/>TelegramNotifier · NullNotifier"]
        end

        subgraph sc["strava package"]
            sclient["StravaClient"]
            tokens["TokenManager"]
            budget["RateBudget"]
            breaker["CircuitBreaker"]
        end

        pg[("PostgreSQL")]
        redis[("Redis<br/>queue · locks · budget · breaker state · stats cache")]
    end

    strava -- "webhook POST" --> hooks
    client_user -- "Bearer or X-API-Key" --> principal
    principal --> read
    principal --> accounts
    accounts -- "users, sessions, invites, settings, chats" --> pg
    accounts -- "login limits, link codes" --> redis
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
    read -- "stats cache (data version key)" --> redis

    browser -- "session cookie" --> gate
    gate --> pages
    gate --> bff
    browser -- "email + password" --> authh
    authh -- "POST /v1/auth/login · register · reset" --> accounts
    pages --> upstream
    bff --> upstream
    upstream -- "Authorization: Bearer" --> principal

    tg_user -. "messages" .-> telegram
    poller -- "getUpdates" --> telegram
    poller --> dispatch
    dispatch --> links
    links --> readapi
    dispatch --> cmds
    dispatch -- "plain text" --> assistant
    assistant -- "plan tool calls" --> anthropic
    assistant -- "rate limit per chat, daily limit per user" --> redis
    cmds --> readapi
    assistant --> readapi
    readapi -- "X-API-Key (service) + X-Acting-User" --> principal
    dispatch -- "sendMessage" --> telegram

    proc -- "enqueue (activity create only)" --> redis
    notify -- "claim (user_id, kind, object_id)" --> pg
    purge -- "delete the user's rows" --> pg
    notify --> notifier
    notifier -- "sendMessage" --> telegram
    digest -- "claim, summary SQL" --> pg
    digest -- "sendMessage" --> telegram
```

The web app and the bot are clients of the read API: neither touches PostgreSQL (ADRs 0011, 0012).
The web holds no API key: each browser's API session token travels sealed in its httpOnly cookie
(ADR 0034). The bot acts as the user its chat is linked to, with a service key the public gateway
cannot impersonate because it strips `X-Acting-User` (ADR 0036). New-activity notifications run in the worker with its own
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
            bot["bot<br/>python -m trainsync.entrypoints.bot<br/>metrics :9101"]
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
    web -- "http://api:8000 + Bearer session token" --> api
    bot -- "http://api:8000 + service key + X-Acting-User" --> api
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

Since Phase 8 (ADR 0035) every user-owned table has `user_id` → `users` (`ON DELETE CASCADE`);
the diagrams draw that edge once per table. Shared rows (built-in exercises, the food catalogue)
have `user_id` NULL.

### Accounts (Phase 8, ADR 0034, ADR 0036)

```mermaid
erDiagram
    users ||--o{ sessions : "signs in with"
    users |o--o{ invites : "creates (created_by)"
    users |o--o| invites : "redeems (used_by)"
    users ||--o{ password_resets : "gets"
    users ||--o| user_settings : "has"
    users ||--o| telegram_chats : "links"
    users ||--o| athletes : "connects"
    users ||--|| user_data_versions : "versions (trigger)"

    users {
        bigint id PK
        varchar email UK "lower-cased"
        text password_hash "argon2id"
        varchar display_name
        varchar role "owner | user, exactly one owner"
        varchar timezone "IANA"
        timestamptz created_at
        timestamptz deleted_at "nullable, purge pending"
    }
    sessions {
        bigint id PK
        bigint user_id FK
        bytea token_hash UK "SHA-256 of the token"
        varchar user_agent "nullable"
        timestamptz created_at
        timestamptz last_seen_at
        timestamptz expires_at "slides, capped"
        timestamptz revoked_at "nullable"
    }
    invites {
        bigint id PK
        bytea code_hash UK
        varchar note "nullable"
        bigint created_by FK "nullable"
        timestamptz created_at
        timestamptz expires_at
        timestamptz used_at "nullable"
        bigint used_by FK "nullable"
        timestamptz revoked_at "nullable"
    }
    password_resets {
        bigint id PK
        bigint user_id FK
        bytea token_hash UK
        timestamptz created_at
        timestamptz expires_at
        timestamptz used_at "nullable"
    }
    user_settings {
        bigint user_id PK, FK
        varchar tone "neutral | hardcore, null = BOT_TONE"
        varchar intensity "normal | savage, nullable"
        varchar profanity "roast | max, nullable"
        varchar lang "en | tr, nullable"
        boolean checkin_enabled "nullable"
        time checkin_time "nullable"
        int checkin_reminder_minutes "nullable"
        varchar quiet_hours "HH:MM-HH:MM, nullable"
        time workout_reminder_time "nullable"
        numeric sugar_limit_g "nullable"
        varchar country "ISO 3166, emergency number"
        boolean stats_digest_enabled "nullable, null = STATS_DIGEST_ENABLED"
        timestamptz updated_at
    }
    user_data_versions {
        bigint user_id PK, FK
        bigint version "bumped by row triggers"
    }
    telegram_chats {
        bigint chat_id PK "Telegram chat"
        bigint user_id FK, UK "one chat per user"
        timestamptz linked_at
    }
    athletes {
        bigint id PK
        bigint user_id FK, UK
    }
```

`user_settings` replaced `chat_settings` (migration 0017); a NULL column means the environment
default. The `/link` code lives in Redis, not in a table. `user_data_versions` (migration 0018,
ADR 0038) gets its row from a trigger on `users`; `bump_user_data_version` increments it on every
insert, update and delete in the tables of `stats/models.py` `VERSIONED_TABLES` (activities,
workouts, sets, exercises, programs and their days and exercises, food logs, nutrition profile,
body metrics, check-ins). The statistics cache key carries it.

### Strava, sync and nutrition

```mermaid
erDiagram
    users ||--o| athletes : "connects"
    athletes ||--o| oauth_tokens : "has"
    athletes ||--o{ activities : "owns"
    athletes ||--o{ sync_runs : "has"
    users ||--o{ notifications : "receives"
    users |o--o{ foods : "own foods (null = shared)"
    users ||--o{ food_favorites : "marks"
    foods ||--o{ food_favorites : "favourited as"
    users ||--o{ food_logs : "logs"
    users ||--o| nutrition_profile : "has"

    users {
        bigint id PK
    }
    athletes {
        bigint id PK
        bigint user_id FK, UK "one athlete per user (ADR 0037)"
        bigint strava_athlete_id UK "one user per athlete"
        boolean active
        timestamptz created_at
    }
    oauth_tokens {
        bigint athlete_id PK, FK
        bigint user_id FK
        bytea access_token_enc
        bytea refresh_token_enc
        timestamptz expires_at
        text scope
    }
    activities {
        bigint id PK
        bigint user_id FK
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
        bigint user_id FK
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
        bigint id PK "no user: routed via the athlete"
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
        bigint user_id FK
        text kind "new_activity | checkin_* | coach_* | stats_digest_*"
        bigint object_id "UK with user_id, kind"
        timestamptz sent_at
    }

    foods ||--o{ food_logs : "logged as"
    foods {
        bigint id PK
        bigint user_id FK "nullable = shared catalogue"
        text name
        text brand "nullable"
        varchar barcode UK "nullable, unique among shared and per user"
        numeric kcal_100g
        numeric protein_100g "nullable = unknown"
        numeric carbs_100g "nullable = unknown"
        numeric fat_100g "nullable = unknown"
        numeric sugars_100g "nullable = unknown (ADR 0032)"
        smallint nova_group "1-4, nullable"
        varchar food_group "free-sugar group, nullable (ADR 0032)"
        text source "manual | openfoodfacts"
        timestamptz created_at
    }
    food_favorites {
        bigint user_id PK, FK
        bigint food_id PK, FK
    }
    food_logs {
        bigint id PK
        bigint user_id FK
        uuid client_id UK "idempotent PUT, unique per user"
        date date
        text meal "breakfast | lunch | dinner | snack"
        bigint food_id FK
        numeric grams
        numeric kcal_100g "snapshot at log time"
        numeric protein_100g "snapshot, nullable"
        numeric carbs_100g "snapshot, nullable"
        numeric fat_100g "snapshot, nullable"
        numeric sugars_100g "snapshot, nullable"
        smallint nova_group "snapshot, nullable"
        varchar food_group "snapshot, nullable"
        timestamptz created_at
    }
    nutrition_profile {
        bigint user_id PK, FK "one per user"
        text sex
        int birth_year
        numeric height_cm
        text activity_baseline "sedentary | light | moderate"
        int kcal_target "nullable"
        int protein_target_g "nullable"
        timestamptz updated_at
    }
```

Nutrition (P6.4, ADR 0019) has no `athlete_id`; it belongs to the user. Body weight for the BMR
estimate comes from `body_metrics` (training), exercise energy from `activities.raw`.

`notifications.object_id` has no foreign key: a row is the idempotency claim for one message
(ADR 0012), kept even if the activity is deleted later; only `user_id` is a foreign key.

### Training (Phase 6, per user since Phase 8)

No `athlete_id`; every table has `user_id` (built-in exercises: NULL). `workouts.strava_activity_id`
is a link, not a foreign key.

```mermaid
erDiagram
    users |o--o{ exercises : "custom (null = built-in)"
    users ||--o{ programs : "owns"
    users ||--o{ workouts : "logs"
    users ||--o{ body_metrics : "enters"
    users ||--o{ daily_checkins : "reports"
    programs ||--o{ program_days : "has"
    program_days ||--o{ program_exercises : "plans"
    exercises ||--o{ program_exercises : "used in"
    program_days |o--o{ workouts : "followed by"
    workouts ||--o{ workout_sets : "logs"
    exercises ||--o{ workout_sets : "of"
    workouts |o--o{ daily_checkins : "reported by"

    users {
        bigint id PK
    }
    exercises {
        int id PK
        bigint user_id FK "nullable = built-in"
        text slug UK "unique among built-ins, and per user"
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
        bigint user_id FK
        text name
        text goal "strength | hypertrophy | general"
        int days_per_week
        int weeks
        boolean active "at most one true per user"
        timestamptz created_at
    }
    program_days {
        bigint id PK
        bigint user_id FK
        bigint program_id FK
        int day_index "UK with program_id"
        text name
        int weekday "0-6, nullable (coach schedule)"
        time start_time "nullable"
    }
    program_exercises {
        bigint id PK
        bigint user_id FK
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
        bigint user_id FK
        uuid client_id UK "client-generated start, unique per user"
        bigint program_day_id FK "nullable"
        timestamptz started_at
        timestamptz ended_at "nullable"
        text notes
        bigint strava_activity_id "nullable, no FK"
    }
    workout_sets {
        bigint id PK
        bigint user_id FK
        uuid client_id UK "client-generated, unique per user"
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
        bigint user_id PK, FK
        date date PK
        numeric weight_kg
    }
    daily_checkins {
        bigint id PK
        bigint user_id FK
        date date UK "local day of the user, unique per user"
        text status "done | partial | skipped | rest | sick_or_injured"
        bigint workout_id FK "nullable, set null"
        text reason_note "nullable"
        numeric sleep_hours "nullable"
        int energy_1_5 "nullable"
        numeric body_weight_kg "nullable, also in body_metrics"
        timestamptz created_at
        timestamptz updated_at
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

    U->>API: GET /auth/strava/login (Bearer session, or the BFF's POST /v1/me/strava/authorize-url)
    API->>API: CurrentUser, sign_state(now, user_id, return_to)
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
        alt athlete bound to another user (ADR 0037)
            API-->>U: 409, nothing written
        end
        API->>DB: BEGIN, upsert athlete (user_id from state, active=true), upsert encrypted tokens, COMMIT
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

The browser only ever talks to the web server. The web holds no API key: the user's API session
token is sealed in the `ts_session` cookie (AES-256-GCM, `DASHBOARD_SESSION_SECRET`) and added as
`Authorization: Bearer` in one place, `lib/upstream.ts` (ADR 0011, ADR 0034). A 401 from the API
clears the cookie and sends the browser to `/login`.

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
    P->>P: openSession(cookie, DASHBOARD_SESSION_SECRET)
    alt no or invalid session
        P-->>U: 307 → /login?next=… (a page) or 401 JSON (an /api/ call)
    else valid
        P->>RSC: render
        par one Suspense block each
            RSC->>UP: api.summary(from, to, sport)
            UP->>API: GET /v1/stats/summary + Bearer token (timeout 10 s, no-store)
            API-->>UP: totals, by sport, last_synced_at
        and
            RSC->>UP: api.weekly(from, to, sport)
            UP->>API: GET /v1/stats/weekly + Bearer token
            API-->>UP: weeks (zero-filled)
        end
        RSC-->>U: streamed HTML: KPI tiles, weekly chart, by sport (no token in it)
    end

    Note over U,BFF: Client components ("Load more" on /activities, the 15 s refresh on /sync)
    U->>P: GET /api/ts/v1/activities?cursor=… (session cookie)
    P->>BFF: valid session
    BFF->>BFF: allowedMethods(path)? (unknown path 404, wrong method 405)
    BFF->>UP: upstreamRequest(GET, path, query)
    UP->>API: GET /v1/activities?cursor=… + Bearer token
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
    UP->>API: PUT /v1/training/... + Bearer token (no browser cookies or headers)
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
    alt no bot token (NullNotifier), or the athlete's user has no linked chat
        N-->>N: disabled
    else activity deleted or athlete gone
        N-->>N: skipped
    else
        N->>DB: INSERT notifications (user_id, new_activity, strava_id) ON CONFLICT DO NOTHING, COMMIT
        alt already claimed
            N-->>N: duplicate: send nothing
        else claimed
            N->>T: send(the user's linked chat, text with link to /activities/{id})
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

## 17. State — daily check-in conversation

State in Redis (`checkin:{chat}:{yyyymmdd}`, 6 h TTL). Every transition raises `seq`; buttons carry
`ci:{yyyymmdd}:{seq}:{action}`, so a button from an older message, a double tap or a redelivered
press no longer matches and gets a polite "earlier question" toast. A redelivered text answer has
an `update_id` the state already saw and is ignored (ADR 0020).

```mermaid
stateDiagram-v2
    [*] --> status : /report, "rapor", or the worker's prompt (seq 0)
    status --> exercise : Done / Partly, active program<br/>(PUT check-in, start or reuse today's workout)
    status --> freeform : Done / Partly, no program
    status --> reason : Skipped
    status --> scale : Rest / Sick (stored, no pushing)
    exercise --> exercise : As planned / ±2.5 kg / typed sets / Skip exercise<br/>(PUT sets, next exercise)
    exercise --> exercise : invalid input → re-prompt
    exercise --> scale : last exercise
    freeform --> freeform : "bench 80x5x3" (PUT sets) / numbered choice
    freeform --> scale : Finish / "done"
    reason --> scale : text, or Skip (hardcore may push here only)
    scale --> sleep : number or Skip
    sleep --> energy : number or Skip
    energy --> done : 1-5 or Skip<br/>(PUT check-in, summary with volume, PRs, streak)
    done --> status : Edit (same client ids: overwrite, never duplicate)
    done --> [*] : TTL 6 h
```

## 18. Sequence — evening check-in prompt

```mermaid
sequenceDiagram
    autonumber
    participant Cron as worker cron (every 5 min)
    participant DB as Postgres
    participant TG as Telegram
    participant Bot as bot process
    participant API as API
    Note over Cron,DB: for each user with a linked chat (Phase 8), in the user's time zone
    Cron->>DB: check-in for the user's local today? prompt / reminder claimed?
    alt before the user's check-in time (default CHECKIN_TIME), or answered
        Cron-->>Cron: nothing
    else due and not sent yet
        Cron->>DB: claim (user_id, checkin_prompt, yyyymmdd) — ON CONFLICT DO NOTHING
        Cron->>TG: sendMessage to the linked chat + 5 status buttons (seq 0)
        Note over Cron,DB: failure → release, next tick retries;<br/>unknown outcome → keep the claim
    else prompt sent ≥ CHECKIN_REMINDER_MINUTES ago, unanswered
        Cron->>DB: claim (user_id, checkin_reminder, yyyymmdd)
        Cron->>TG: one reminder
    end
    TG-->>Bot: callback_query (getUpdates)
    Bot->>API: PUT /v1/checkins/{date} (status) + service key + X-Acting-User
    Bot->>TG: answerCallbackQuery, remove buttons, next question
```

## 19. Sequence — log a set with retry

The client id is created once per set row, so a double tap, a retry and a replay from the queue
are the same `PUT` (ADR 0017). Gym Wi-Fi drops the answer, not the request, in the second case.

```mermaid
sequenceDiagram
    autonumber
    participant UI as Workout screen
    participant Q as Retry queue (localStorage)
    participant BFF as BFF /api/ts
    participant API as API
    participant DB as Postgres

    Note over UI,API: the workout itself was started the same way: PUT /v1/training/workouts/{uuid W}
    UI->>UI: tap ✓ (row already has client_id = uuid A)
    UI->>BFF: PUT /v1/training/workouts/42/sets/A (CSRF token, JSON)
    BFF->>API: PUT … + Bearer token
    API->>DB: INSERT … ON CONFLICT (user_id, client_id) DO UPDATE … RETURNING xmax = 0
    DB-->>API: row, created
    API-->>UI: 201 set
    UI->>UI: second tap on the same row: same uuid A
    UI->>BFF: PUT …/sets/A
    BFF->>API: PUT …/sets/A
    API->>DB: upsert, conflict → update
    API-->>UI: 200, same body (still one row)
    UI->>BFF: PUT …/sets/B (next set)
    BFF->>API: PUT …/sets/B
    API->>DB: upsert (stored)
    API--xUI: answer lost (Wi-Fi drop, status 0)
    UI->>Q: keep {path …/sets/B, body}
    Note over UI,Q: browser fires `online`, or the next write succeeds
    Q->>BFF: PUT …/sets/B (same path, same body)
    BFF->>API: PUT …/sets/B
    API->>DB: upsert, conflict → update
    API-->>Q: 200, entry leaves the queue (still one row)
    Note over Q,API: a 4xx answer is final: the entry is dropped and shown as an error
```

## 20. Sequence — rest timer and a backgrounded tab

Timers store absolute times and render `endsAt − now()`, so frozen intervals in a backgrounded
tab or behind a locked screen do not matter (ADR 0021).

```mermaid
sequenceDiagram
    autonumber
    participant U as Lifter
    participant UI as Workout screen
    participant LS as localStorage
    participant OS as Browser / phone

    U->>UI: log set 2 of Bench Press (rest 90 s)
    UI->>LS: save {endsAt: now + 90 000, alerted: false}
    loop every 250 ms while visible
        UI->>UI: render ceil((endsAt − now) / 1000)
    end
    U->>OS: lock the screen
    OS-->>UI: intervals throttled or frozen
    Note over UI: 3 minutes pass, nothing renders
    U->>OS: unlock
    OS-->>UI: visibilitychange / next tick
    UI->>UI: remaining = max(0, endsAt − now) = 0 → 0:00
    alt zero passed less than 60 s ago and not alerted
        UI->>OS: vibrate, beep, optional Notification
        UI->>LS: alerted = true
    else asleep long past zero
        UI->>LS: alerted = true (no late alarm)
    end
    U->>UI: reload the page
    UI->>LS: read state for workout 42
    LS-->>UI: endsAt, alerted (timer restored, no repeated alert)
```

## 21. Deployment — production on the MacBook (Phase 7)

```mermaid
flowchart TB
    strava[("Strava<br/>OAuth + webhooks")]
    vercel["Vercel<br/>web/ BFF (server-side)"]
    gha["GitHub Actions<br/>public-check (every 6 h) · uptime (every 15 min)"]
    tg["Telegram"]

    subgraph ts["Tailscale"]
        funnel["Funnel · TLS for &lt;mac&gt;.&lt;tailnet&gt;.ts.net<br/>:443 real · :8443 demo"]
    end

    subgraph mac["MacBook (always on, no AC sleep)"]
        agent["LaunchAgent com.trainsync.stack<br/>at login: wait for Docker → mac-prod.sh up"]
        deploy["make deploy / make rollback<br/>(green CI, pre-deploy backup, migrate, smoke)"]
        icloud[("iCloud Drive<br/>trainsync-backups (*.dump.age)")]
        demo["compose.demo.yml · 127.0.0.1:8081<br/>read-only demo (diagram 25)"]
        subgraph dd["Docker Desktop · compose.prod.yml"]
            gw["gateway (Caddy)<br/>127.0.0.1:8080 · route allowlist<br/>strips X-Acting-User · /v1/auth/* 30/min"]
            api["api"]
            worker["worker"]
            bot["bot"]
            backup["backup<br/>nightly pg_dump + age · retention · weekly restore check"]
            subgraph backend["backend network (internal)"]
                pg[("postgres")]
                rd[("redis")]
            end
        end
    end

    strava -- "https://host/auth/strava/callback<br/>https://host/webhooks/strava" --> funnel
    vercel -- "https://host/v1/* + Bearer session token" --> funnel
    gha -- "allowlisted → forwarded<br/>everything else → 404" --> funnel
    funnel -- "http 127.0.0.1:8080" --> gw
    gw --> api
    api --> pg
    api --> rd
    worker --> pg
    worker --> rd
    bot --> api
    agent -. "docker compose up" .-> dd
    deploy -. "images tagged by git SHA" .-> dd
    funnel -- "http 127.0.0.1:8081" --> demo
    backup --> pg
    backup -- "encrypted dumps" --> icloud
    worker -. "reads backup age" .-> icloud
    backup -. "backup / restore-check result" .-> tg
    gha -. "uptime: down / recovered" .-> tg
    worker -. "stack alerts: start / clear" .-> tg
```

## 22. Sequence — nightly backup and weekly restore check (P7.4, ADR 0024)

```mermaid
sequenceDiagram
    participant L as backup loop
    participant PG as postgres
    participant D as BACKUP_DIR (iCloud Drive)
    participant S as scratch Postgres (in the backup container)
    participant T as Telegram
    loop every minute
        L->>D: due? (slot passed, no backup since)
    end
    L->>PG: BEGIN REPEATABLE READ; pg_export_snapshot()
    L->>PG: row counts of every table (same snapshot)
    L->>PG: pg_dump -Fc --snapshot
    L->>D: age -r recipient → .name.partial, then rename .counts.json and .dump.age
    L->>D: retention (7 daily / 4 weekly / 6 monthly)
    alt restore-check weekday and identity mounted
        L->>S: age -d (authenticated) → pg_restore
        L->>S: row counts
        L->>L: compare with .counts.json
        L->>T: passed / FAILED
    else backup failed
        L->>T: backup FAILED, retry in 1 h
    end
```

## 23. Activity — make deploy and make rollback (P7.5, ADR 0026)

```mermaid
flowchart TD
    start(["make deploy"]) --> clean{"clean worktree, branch main,<br/>HEAD == origin/main after fetch?"}
    clean -- no --> refuse(["refuse · deploys.log"])
    clean -- yes --> ci{"gh run list --commit SHA --workflow ci<br/>completed success?"}
    ci -- no --> refuse
    ci -- yes --> build["build images, TRAINSYNC_TAG = SHA[:12]"]
    build --> backup["backup now predeploy&lt;sha7&gt;"]
    backup --> before["alembic current → rev_before"]
    before --> migrate["one-shot migrate: alembic upgrade head → rev_after"]
    migrate --> state["deploy-state: current = new, previous = old, rev_before"]
    state --> up["up -d"]
    up --> smoke{"smoke: /health/ready via gateway,<br/>/v1/sync/status with an API key, bot getMe"}
    smoke -- ok --> done(["success · deploys.log · Telegram"])
    smoke -- fail --> rb
    build & backup & migrate -- fail --> abort(["abort: the old version keeps running · Telegram"])

    rbstart(["make rollback"]) --> rb{"previous deploy recorded<br/>and its image present?"}
    rb -- no --> rbrefuse(["refuse"])
    rb -- yes --> crossed{"migrations between<br/>rev_before and rev_after?"}
    crossed -- none --> old["up -d with the previous tag"]
    crossed -- "all reversible = True" --> down["alembic downgrade rev_before<br/>(new image: it has the downgrade code)"]
    down --> old
    crossed -- "any reversible = False" --> restore(["refuse · print the restore steps<br/>(pre-deploy backup, then rollback --restored)"])
    old --> rbdone(["smoke test · deploy-state: current = previous · Telegram"])
```

## 24. State — uptime and stack alerts (P7.8, ADR 0027)

External uptime, per target (`src/trainsync/ops/uptime.py`, run by `.github/workflows/uptime.yml`
every 15 minutes; state in the Actions cache). Threshold 2: flapping (fail, ok, fail, ok) never
reaches `down`.

```mermaid
stateDiagram-v2
    [*] --> up
    up --> up: ok
    up --> failing: fail (n = 1)
    failing --> up: ok
    failing --> failing: fail, n + 1 below 2
    failing --> down: fail, n + 1 reaches 2 / send DOWN
    down --> down: fail / nothing
    down --> up: ok / send RECOVERED
    note right of down
        a failed send keeps the old state:
        the next run sends again
    end note
```

Stack alerts, per condition (`src/trainsync/modules/notifications/alerts.py`, worker cron every 5 minutes; state
in Redis `alert:<condition>`). Grace: 30 min for the circuit breaker, 0 for the others (their
threshold is in the observation: dead letters > 0, backup > 36 h, sync > 2 h).

```mermaid
stateDiagram-v2
    [*] --> ok
    ok --> pending: bad (bad_since = now)
    pending --> ok: ok / nothing
    pending --> pending: bad, inside the grace
    pending --> alerted: bad, grace over / send alert
    alerted --> alerted: bad / nothing
    alerted --> ok: ok / send resolved
    note left of pending
        unknown (no breaker report,
        never synced) changes nothing
    end note
```

## 25. Deployment — public read-only demo (P7.9, ADR 0028)

```mermaid
flowchart TB
    visitor["Visitor (README link)"]
    preview["Vercel preview<br/>web/ BFF · demo account<br/>demo@trainsync.invalid"]

    subgraph ts["Tailscale"]
        funnel["Funnel :8443"]
    end

    subgraph dd["Docker Desktop · compose.demo.yml (project trainsync-demo)"]
        gw["gateway (same Caddy image + routes.toml)<br/>127.0.0.1:8081"]
        api["api · DEMO_MODE=true<br/>DemoReadOnlyMiddleware: writes → 403<br/>except login / logout"]
        subgraph backend["backend network (internal)"]
            pg[("postgres · demo-pgdata")]
            rd[("redis")]
            fs["fake_strava (no real Strava)"]
            worker["demo worker<br/>reset cron 03:00 UTC"]
            seed["seed (one-shot on up)<br/>python -m trainsync.entrypoints.demo reset"]
        end
    end

    visitor --> preview
    preview -- "POST /v1/auth/login, then GET /v1/* + Bearer" --> funnel
    funnel -- "http 127.0.0.1:8081" --> gw
    gw --> api
    api -- "reads" --> pg
    api --> rd
    seed -- "wipe + synthetic dataset<br/>(seed.py, fixed RNG)" --> pg
    worker -- "same reset nightly" --> pg
    api -. "Strava URLs point here" .-> fs
```

## 26. Sequence — the coach during a workout (P6.11, ADR 0030)

Every message claims a `notifications` row first; quiet hours drop it; check-in workouts get none.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (web / bot)
    participant API as API
    participant Q as arq (Redis)
    participant W as Worker (coach jobs)
    participant T as Telegram

    C->>API: PUT /v1/training/workouts/{client_id} (201)
    API->>Q: coach_workout_started:{id}
    Q->>W: coach_workout_started
    W->>T: start line (savage or tone pack)
    C->>API: PUT …/sets/{client_id} (201)
    API->>Q: coach_set_logged:{set id}
    Q->>W: coach_set_logged
    alt below plan (reps < rep_min or lighter than the suggestion)
        W->>T: under target (once per exercise per workout)
    end
    W->>Q: coach_rest_over, deferred to completed_at + rest_seconds
    Q->>W: coach_rest_over
    alt still the latest set, planned sets left, not late
        W->>T: "kalk, sıradaki set"
    end
    C->>API: POST …/finish
    API->>Q: coach_workout_finished:{id}
    Q->>W: coach_workout_finished
    W->>T: summary + PRs + verdict (good / missing sets)
```

## 27. Sequence — /lang and the chat's language (P6.12, ADR 0031)

`BOT_LANG` is the default; a stored choice wins. The bot sets the language once per update, the
worker once per job, read at send time. Since Phase 8 the choice is the linked user's
`user_settings.lang` (ADR 0036).

```mermaid
sequenceDiagram
    autonumber
    participant U as User (linked Telegram chat)
    participant B as Bot
    participant API as API
    participant DB as Postgres (user_settings)
    participant W as Worker

    U->>B: /lang
    B->>API: GET /v1/telegram/chats/{chat} (user id + settings, cached BOT_CHAT_CACHE_S)
    API->>DB: SELECT telegram_chats, user_settings
    B-->>U: "Türkçe" / "English" buttons
    U->>B: press "English"
    B->>API: PATCH /v1/me/settings {"lang": "en"} + service key + X-Acting-User
    API->>DB: upsert user_settings
    B->>B: drop the chat's cache entry
    B-->>U: confirmation in English (savage line in savage mode)
    Note over W: a reminder, check-in or notification for this user is due
    W->>DB: SELECT the user's settings and linked chat
    W-->>U: message in English
```

## 28. Activity — a chat message in savage mode, profanity and the guardrails (P6.13, ADR 0032)

Distress first, then pain, then the triggers. The calm replies never get a max opener; every other
savage message does in max, unless it already carries a max line.

```mermaid
flowchart TD
    M[chat message] --> D{distress?<br/>guilt, threw up, not eating,<br/>self-hate, binge}
    D -- yes --> C1[calm SAFETY_DISTRESS reply<br/>no swearing, no assistant]
    D -- no --> P{pain, injury, illness?}
    P -- yes --> C2[calm SAFETY_PAIN reply<br/>no swearing, no assistant]
    P -- no --> S{savage in effect?<br/>configured, not /yumusak}
    S -- no --> N[tone pack / assistant]
    S -- yes --> F{unhealthy choice?<br/>junk, sugar, alcohol,<br/>cigarettes, up late}
    F -- yes --> R1[food_roast line + one move<br/>+ day's target unchanged]
    F -- no --> E{excuse?}
    E -- yes --> R2[excuse roast + one action today]
    E -- no --> N
    R1 & R2 & N --> L{profanity max?<br/>/swear, else BOT_PROFANITY}
    L -- roast --> OUT[send]
    L -- max --> O[lines from the max pools;<br/>max_opener in front of a message<br/>with no savage line]
    O --> OUT
    C1 & C2 --> OUT
```

## 29. Layers — code layout and allowed imports (ADR 0033)

Imports only point down. import-linter checks the layer order, the independence of the
entrypoints, the module order and that `ops` stays standard-library only (`make lint`). Every
module may import any module's `models.py`. `stats` has its own layer between `chat` and
`admin | users` because it reads check-ins, nutrition rules and user settings (ADR 0038).

```mermaid
flowchart TB
  subgraph E["entrypoints"]
    direction LR
    eapi["api"] ~~~ eworker["worker"] ~~~ ebot["bot"] ~~~ edemo["demo"] ~~~ ecli["cli"]
  end
  subgraph M["modules"]
    notifications --> chat
    chat --> stats
    stats --> users & admin
    users & admin --> coach & checkin & nutrition & sync
    coach & checkin & nutrition --> training
    training & nutrition & sync --> activities
    activities --> strava
    sync --> strava
    strava --> auth
  end
  subgraph I["integrations"]
    direction LR
    istrava["strava"] ~~~ itelegram["telegram"] ~~~ ianthropic["anthropic"] ~~~ ioff["openfoodfacts"]
  end
  C["core"]
  E --> M --> I --> C
  O["ops (stdlib only)"]
```

## 30. Sequence — sign-up with an invite, then login through the BFF (P8.1, P8.7, ADR 0034)

The owner hands out the invite; nothing is mailed. The browser never sees the API token: the BFF
seals it into the httpOnly `ts_session` cookie.

```mermaid
sequenceDiagram
    autonumber
    actor O as Owner (Mac shell)
    actor U as New user (browser)
    participant CLI as cli invite create
    participant BFF as Web BFF (/api/auth/*)
    participant API as trainsync API
    participant R as Redis (limits)
    participant DB as PostgreSQL

    O->>CLI: invite create --note "Ayşe"
    CLI->>DB: INSERT invites (code_hash, expires_at = now + INVITE_TTL_DAYS)
    CLI-->>O: code + DASHBOARD_PUBLIC_URL/register?invite=CODE
    O-->>U: sends the link
    U->>BFF: POST /api/auth/register {email, password, invite_code} (same Origin)
    BFF->>API: POST /v1/auth/register
    API->>R: registrations per address < REGISTER_MAX_PER_HOUR?
    alt REGISTRATION_MODE=closed
        API-->>BFF: 403
    else invite missing, used or expired
        API-->>BFF: 400
    else email taken
        API-->>BFF: 409
    else ok
        API->>DB: BEGIN, INSERT users (argon2id hash, role user), mark invite used, COMMIT
        API-->>BFF: 201 me
        BFF->>API: POST /v1/auth/login {email, password}
        API->>R: failures for this email / address under LOGIN_MAX_FAILURES*?
        API->>DB: verify argon2id, INSERT sessions (SHA-256 of a random 32-byte token)
        API-->>BFF: {token, expires_at, user}
        BFF->>BFF: seal token (AES-256-GCM, DASHBOARD_SESSION_SECRET)
        BFF-->>U: 303 → next, Set-Cookie ts_session (httpOnly, Secure, SameSite=Lax) + ts_csrf
    end

    Note over U,API: Later requests
    U->>BFF: GET a page (ts_session)
    BFF->>API: GET /v1/... + Authorization: Bearer token
    API->>DB: session by token hash: not revoked, not expired, slide expires_at (at most every SESSION_TOUCH_INTERVAL_S, capped at SESSION_MAX_AGE_DAYS)
    alt valid
        API-->>BFF: the user's data only
    else revoked or expired
        API-->>BFF: 401
        BFF-->>U: clear ts_session, 307 → /login
    end
```

## 31. Sequence — linking a Telegram chat with /link (P8.4, ADR 0036)

One bot serves every account. The bot never touches the database; it acts as the linked user
with its service key and `X-Acting-User`, a header the public gateway strips.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant BFF as Web BFF
    participant API as trainsync API
    participant R as Redis
    participant DB as PostgreSQL
    participant B as Bot
    participant TG as Telegram

    U->>BFF: "Link Telegram"
    BFF->>API: POST /v1/me/telegram/code + Bearer token
    API->>R: SET link code → user_id (TTL TELEGRAM_LINK_CODE_TTL_MINUTES)
    API-->>BFF: {code, command: "/link CODE", bot_url (with TELEGRAM_BOT_USERNAME)}
    BFF-->>U: shows the code
    U->>TG: /link CODE (to the bot)
    TG-->>B: getUpdates
    B->>API: GET /v1/telegram/chats/{chat_id} + service key
    API-->>B: 404 chat not linked
    B->>API: POST /v1/telegram/chats/{chat_id}/link {code} + service key
    API->>R: GET + DELETE code (single use)
    alt unknown, used or expired code
        API-->>B: 400
        B-->>TG: "invalid or expired code"
    else ok
        API->>DB: upsert telegram_chats (chat_id → user_id, the user's previous chat unlinked)
        API-->>B: {chat_id, user_id, display_name, settings}
        B->>B: cache chat → user (BOT_CHAT_CACHE_S)
        B-->>TG: "linked" in the user's language
    end

    Note over U,TG: Afterwards
    U->>TG: /week
    TG-->>B: getUpdates
    B->>API: GET /v1/stats/weekly + service key + X-Acting-User: user_id
    API-->>B: that user's weeks only
    B-->>TG: reply in the user's tone and language

    Note over B,TG: Any other chat that is not linked
    B-->>TG: one hint: link your account at DASHBOARD_PUBLIC_URL (nothing else runs)
```

## 32. Sequence — progress summary with the versioned cache (P8.10, ADR 0038)

Short windows are computed every time; windows of `STATS_CACHE_MIN_DAYS` or more go through
Redis. Any write to a table the statistics read bumps the version, so the next request builds a
new key; the old entry is never read again and expires after `STATS_CACHE_TTL_S`.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (BFF, bot, curl)
    participant API as trainsync API
    participant DB as PostgreSQL
    participant R as Redis

    C->>API: GET /v1/stats/summary?period=12m
    API->>API: resolve period → local days in the user's zone, previous period
    alt window < STATS_CACHE_MIN_DAYS
        API->>DB: one aggregate query per block (bounds = UTC instants of local midnights)
        DB-->>API: sums, counts, e1RM maxima grouped by local day
    else long window
        API->>DB: SELECT version FROM user_data_versions WHERE user_id = :me
        DB-->>API: version
        API->>R: GET stats:{user}:{version}:summary:{hash of params}
        alt hit
            R-->>API: cached JSON
        else miss (or Redis down: computed, not stored)
            API->>DB: one aggregate query per block, current and previous period
            DB-->>API: rows
            API->>API: shape blocks, change and change_pct
            API->>R: SET key JSON EX STATS_CACHE_TTL_S
        end
    end
    API-->>C: 200 totals + endurance, strength, consistency, nutrition, body

    Note over DB: later: any INSERT / UPDATE / DELETE on a versioned table<br/>(API, bot, sync worker, demo seed, psql)
    DB->>DB: trigger bump_user_data_version → version + 1
```

## 33. Sequence — Monday progress digest (P8.11, ADR 0038)

The 1st of the month works the same way with `stats_digest_month` and last month.

```mermaid
sequenceDiagram
    autonumber
    participant Cron as worker cron digest_tick (every 5 min)
    participant DB as PostgreSQL
    participant S as stats service
    participant TG as Telegram

    Cron->>DB: recipients: users with a linked chat and their settings
    loop each recipient, in the user's time zone
        alt digests off (no bot token, STATS_DIGEST_ENABLED=false, stats_digest_enabled=false)
            Cron-->>Cron: skip
        else not Monday, or before STATS_DIGEST_TIME local
            Cron-->>Cron: nothing due
        else quiet hours
            Cron-->>Cron: hold until they end (same local day)
        else due
            Cron->>DB: claim (user_id, stats_digest_week, first day of last week) — ON CONFLICT DO NOTHING
            alt already claimed
                Cron-->>Cron: sent before, nothing
            else claimed
                Cron->>S: summary of last_week as the user
                S->>DB: aggregate queries (local days)
                S-->>Cron: StatsSummary
                alt nothing trained, logged or checked in
                    Cron-->>Cron: keep the claim, send nothing
                else
                    Cron->>Cron: progress message (user's language, tone, verdict line)
                    Cron->>TG: sendMessage to the linked chat
                    Note over Cron,DB: definite failure → release the claim, next tick retries,<br/>unknown outcome → keep it
                end
            end
        end
    end
```
