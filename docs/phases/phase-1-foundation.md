# Phase 1 — Foundation, OAuth, Strava client

Goal: a running stack that can connect a Strava account and make authenticated, resilient calls.

## Tasks
1. Project setup: `uv`, `pyproject.toml`, ruff, mypy, pytest config, `src/` layout from CLAUDE.md.
2. `docker-compose.yml`: postgres, redis, fake-strava, api, worker.
3. Settings with pydantic-settings (`.env.example` committed, `.env` ignored).
4. SQLAlchemy models + first Alembic migration for all tables in `docs/architecture.md`.
5. Fernet token encryption helper.
6. `fake_strava` app: `/oauth/authorize`, `/oauth/token`, `/api/v3/athlete`,
   `/api/v3/athlete/activities`, `/api/v3/activities/{id}`, with seeded fake activities.
   Configurable via env: latency, error rate, rate-limit budget (returns `X-RateLimit-*` headers and 429).
7. OAuth endpoints: login redirect with signed `state`, callback with code exchange.
8. Strava client: shared AsyncClient, timeouts, token refresh with Redis lock, 401 handling,
   retry with exponential backoff + full jitter, rate-limit header parsing.
9. Structured logging + `/health/live`, `/health/ready`.

## Acceptance criteria
- `docker compose up` starts everything; `/health/ready` returns 200.
- Connecting through fake_strava stores an athlete and encrypted tokens.
- Unit tests: backoff timing bounds, retryable vs non-retryable status codes,
  rate-limit header parsing, token refresh race (two concurrent calls → one refresh).
- ruff, mypy, pytest all green.
