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

```
src/trainsync/
  api/            # FastAPI routers, request/response schemas, dependencies
  strava/         # Strava HTTP client, OAuth, rate limiter, circuit breaker
  sync/           # backfill, incremental sync, webhook processing (job functions)
  db/             # SQLAlchemy models, session, repositories
  core/           # settings, logging, metrics, crypto
  worker.py       # arq WorkerSettings
  main.py         # FastAPI app factory
fake_strava/      # standalone FastAPI app that imitates the Strava API (dev + tests + load tests)
tests/
  unit/
  integration/
loadtest/         # locust files
migrations/       # alembic
```

## Commands

```
uv sync
docker compose up -d postgres redis fake-strava
uv run alembic upgrade head
uv run uvicorn trainsync.main:create_app --factory --reload
uv run arq trainsync.worker.WorkerSettings
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy src
make verify          # lint + mypy + unit + integration — must be green before merge
```

## Rules

- All outbound calls to Strava go through `strava/client.py`. Nothing else imports httpx for Strava.
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
