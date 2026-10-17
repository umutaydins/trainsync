# Phase 4 — Observability, load test, CI, README

Goal: prove it works under failure and load, and make the repo presentable.

## Tasks
1. Prometheus metrics:
   - `strava_requests_total{endpoint,status}`, `strava_request_duration_seconds{endpoint}`
   - `strava_retries_total`, `strava_circuit_state`, `strava_ratelimit_usage_ratio{window}`
   - `sync_jobs_total{kind,status}`, `webhook_events_total{aspect,status}`
   - `http_request_duration_seconds{route}`
2. Fault-injection test suite (pytest, marked `fault`): 429 bursts, 5xx bursts, timeouts,
   duplicate and out-of-order webhooks, worker restart.
3. Locust load test (`loadtest/`): webhook POST and read API against the docker stack + fake_strava.
   Record RPS, p50/p95/p99 and error rate in `README.md`.
4. GitHub Actions: `uv sync` → ruff → mypy → pytest (unit + integration with service containers) → docker build.
5. README: what it is, why I built it, architecture diagram, failure modes table,
   how to run, load-test results, design decisions (link ADRs).

## Acceptance criteria
- CI green on main.
- README contains real measured numbers (no placeholders).
- At least 4 ADRs in `docs/decisions/` (e.g. arq vs Celery, rate-limit priorities, webhook ack-then-process,
  fetch-on-event instead of trusting event payloads).
