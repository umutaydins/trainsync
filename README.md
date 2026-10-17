# trainsync

A self-hosted backend that keeps a complete, always-fresh copy of my Strava training data in
PostgreSQL and serves it through my own API.

I wanted to run my own analyses on my training history (weekly volume, trends by sport) without
depending on Strava's UI, its availability, or its rate limits every time I query my data.

## What it does
- Connects a Strava account via OAuth and backfills the full activity history
- Receives Strava webhooks and applies changes asynchronously (create / update / delete / deauthorize)
- Runs incremental syncs as a safety net for missed webhooks
- Serves activities and weekly stats through a typed HTTP API

## How it stays reliable
- Rate-limit-aware Strava client: reads `X-RateLimit-*` headers, two-priority budget, waits for window reset on 429
- Retries with exponential backoff and jitter, circuit breaker, proactive token refresh with a distributed lock
- Idempotent upserts, resumable backfill checkpoints, deduplicated webhook events, dead-letter retries

See [docs/architecture.md](docs/architecture.md) for flows and the failure-mode table, and
[docs/diagrams.md](docs/diagrams.md) for component, ER, class, sequence and state diagrams.

## Stack
Python 3.12 · FastAPI · httpx · PostgreSQL · SQLAlchemy 2 · Alembic · Redis · arq · Prometheus ·
pytest · testcontainers · Docker Compose · GitHub Actions

## Run locally
```
cp .env.example .env
docker compose up -d
uv run alembic upgrade head
```

## Load test results
_TODO — fill in after Phase 4 with measured numbers._

## Status
- [ ] Phase 1 — Foundation, OAuth, Strava client
- [ ] Phase 2 — Sync engine
- [ ] Phase 3 — Webhooks and read API
- [ ] Phase 4 — Observability, load test, CI
