# 0010 — Prometheus metrics: one registry per process

- Status: accepted
- Date: 2026-10-18

## Context
The API (one uvicorn process) and the workers (one or more `arq` processes) are separate
processes, often in separate containers. Most interesting metrics (Strava calls, retries,
breaker state, job outcomes) are produced in the workers. `prometheus_client` keeps metrics in
process memory.

## Decision
Every process uses the default in-memory registry and serves it itself:
- The API: `GET /metrics` (not in the OpenAPI document, no API key, so a standard scrape config
  works; it exposes counts only, never data).
- Each worker: `prometheus_client.start_http_server(WORKER_METRICS_PORT)` (default 9100, 0 turns
  it off), started in the worker's `startup` and stopped in `shutdown`.

Prometheus scrapes each process as its own target and aggregates across them with
`sum by (…)`. `strava_circuit_state` is a per-process gauge. That matches the breaker, which is
per process too (ADR 0005).

Labels are bounded: endpoint templates (`/activities/{id}`), route templates (`/v1/activities`,
or `unmatched` for unknown paths), status codes, and small enums for job and webhook outcomes.

## Alternatives considered
- **`prometheus_client` multiprocess mode** (`PROMETHEUS_MULTIPROC_DIR`): it exists for several
  workers of *one* server sharing a port (gunicorn). Our processes are independent and each can
  listen on its own port. Multiprocess mode needs a shared directory, cleanup of dead PIDs'
  files, and loses some metric types (no live gauges without extra modes). Its costs buy us
  nothing here.
- **Pushgateway**: meant for short batch jobs. Our workers are long-running.
- **Workers report to the API through Redis**: a home-made metrics pipeline.

## Consequences
- Each worker container exposes one more port. Compose maps the worker's 9100.
- Counters reset when a process restarts, which Prometheus' `rate()` handles.
- Scaling to N workers means N scrape targets (service discovery or a static list).
