# trainsync — Claude Code instructions

Personal backend service that syncs my training data from the Strava API into my own
database and serves it through a clean HTTP API. Backend only — no frontend.

Read `docs/architecture.md` before any change. Work phase by phase from `docs/phases/`, one task
at a time from `docs/tasks/` (id order, respect `depends_on`). Do not start a phase until the
previous phase's acceptance criteria pass. Diagrams live in `docs/diagrams.md`; update them when
the design changes.

## Stack

- Python 3.12, managed with `uv`
- FastAPI (HTTP API), httpx `AsyncClient` (outbound HTTP)
- PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic
- Redis 7 + arq (background jobs, cron)
- structlog (JSON logs), prometheus-client (metrics)
- pytest, pytest-asyncio, respx, testcontainers
- ruff (lint + format), mypy (strict on `src/`)
- Docker Compose for local stack, GitHub Actions for CI

## Layout

Modular monolith, four layers, enforced by import-linter in `make lint` (ADR 0033):
`entrypoints → modules → integrations → core`.

```
src/trainsync/
  core/            # settings, db engine/session + ORM base, logging, metrics, crypto, clock,
                   # errors, FastAPI deps, job queue, http client, password/token hashing, redis
  integrations/    # outbound clients only, never import modules
    notifier.py    #   Notifier interface (Telegram today, another channel later)
    strava/        #   Strava HTTP client, rate limiter, retries, circuit breaker, budget
    telegram/      #   Bot API client, Telegram notifier
    anthropic/     #   Claude Messages API call, the assistant's tool definitions
    openfoodfacts/ #   product lookup
  modules/         # one package per domain: router.py, schemas.py, repository.py, models.py,
                   # tasks.py (worker jobs) where they apply; models.py = the tables
    auth/          #   users, sessions, invites, reset links, login limits, CurrentUser (/v1/auth)
    strava/        #   OAuth bound to the signed-in user, athletes, encrypted tokens (/v1/me/strava)
    activities/    #   activity upserts and reads (/v1/activities)
    sync/          #   backfill, incremental, webhooks, deauthorize/disconnect (/v1/sync,
                   #   /webhooks/strava)
    training/      #   exercises, programs, workouts, sets, progression, plates (/v1/training)
    checkin/       #   daily check-ins, streaks (/v1/checkins)
    nutrition/     #   foods, favourites, logs, energy balance (/v1/nutrition)
    coach/         #   voice, guardrails, savage lines; packs/ = message packs (tr/en, tones)
    users/         #   /v1/me: profile, password, sessions, per-user settings, export, deletion
    admin/         #   owner-only /v1/admin: invites, accounts, reset links
    stats/         #   weekly totals and progress statistics (/v1/stats), SQL per local day,
                   #   Redis cache keyed by the trigger-bumped user_data_versions (ADR 0038);
                   #   own layer between chat and admin|users
    chat/          #   Telegram conversation over the read API (bot features, read-API client),
                   #   chat links (/v1/me/telegram, /v1/telegram/chats)
    notifications/ #   worker senders per user: new activity, check-in, coach, stack alerts
    models.py      #   imports every models.py (complete Base.metadata)
  entrypoints/     # thin composition roots
    api/           #   app factory, middleware (incl. demo read-only), health, router registry
    worker/        #   arq WorkerSettings, cron registry
    bot/           #   long polling, dispatcher, feature wiring
    cli/           #   owner tools: invite create|list|revoke, owner set-password|reset-link
    demo/          #   read-only demo seed and reset
  ops/             # backup + retention + alerts, standard library only (backup image)
web/src/           # Next.js: app/ (routes only), features/<domain>/, lib/ (BFF, generated
                   # API types, session, preferences, config), components/ui/ (primitives),
                   # i18n/ (next-intl; tr/en messages per feature), styles/ (design tokens);
                   # ESLint boundaries
fake_strava/       # standalone FastAPI app that imitates the Strava API (dev + tests + load tests)
tests/{unit,integration}/<mirror of src/trainsync>/   tests/fault/ (end-to-end scenarios)
config/            # messages.local.example.yaml (the real file is git-ignored)
deploy/            # gateway (Caddy), backup image, launchd, compose overlays
scripts/           # owner CLIs and checks (deploy, invite, owner, strava-subscription,
                   # prod/demo/public checks)
loadtest/          # locust files
migrations/        # alembic
```

## Commands

```
uv sync
docker compose up -d postgres redis fake-strava
uv run alembic upgrade head
uv run uvicorn trainsync.entrypoints.api.app:create_app --factory --reload
uv run arq trainsync.entrypoints.worker.settings.WorkerSettings
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy   # src/ + fake_strava/
make verify          # lint + mypy + unit + integration — must be green before merge
make compose-smoke   # build + start the compose stack, OAuth smoke test, tear down
docker compose up -d --build   # full local stack (migrations run in the one-shot `migrate` service)
```

## Rules

- All outbound calls to Strava go through `integrations/strava/client.py`. Nothing else imports httpx for Strava.
- One shared `httpx.AsyncClient` per process, created in the app/worker lifespan. Explicit timeouts always.
- Every write that can be repeated (upserts, webhook events, sync checkpoints) must be idempotent.
- The webhook POST handler only validates, persists and enqueues. No Strava calls inside it.
- Tokens are encrypted at rest (Fernet key from settings). Never log tokens or secrets.
- Settings come from environment variables via pydantic-settings. No hard-coded URLs except defaults.
- Tests never hit the real Strava API. Use respx for unit tests and `fake_strava` for integration and load tests.
- Every non-obvious design choice gets a short ADR in `docs/decisions/` (template in `0000-template.md`).
- Keep functions small and typed. No `Any` in public signatures.
- Time-dependent code takes an injected clock/sleep; tests never rely on real sleeps.
- Never make CI green by skipping tests or loosening ruff/mypy config.
- After each phase, update the "Status" section in `README.md`.
