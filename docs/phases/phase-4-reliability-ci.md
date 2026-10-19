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

## Evidence

Phase criteria:

| Criterion | Proven by |
|---|---|
| CI green on `main` | **Not verifiable from this clone: it has no git remote** (see `QUESTIONS.md`). Every command CI runs passes locally on 2026-10-18: `make verify` (lint, mypy strict, 226 unit + 90 integration tests, branch coverage 97% ≥ 85%), `make test-fault` (11 tests), `make audit` (no known vulnerabilities), `make compose-smoke`, and the docker job's image checks (non-root uid 10001, `HEALTHCHECK`, no dev/test/load-test packages). |
| README contains real measured numbers | README → "Load test results": two `make loadtest` runs from 2026-10-18 (mixed 50 users; webhooks only 25 users) with machine description; no placeholders (`grep -n "TODO\|placeholder" README.md` is empty) |
| At least 4 ADRs | 10 ADRs in `docs/decisions/` (0001–0010), all linked from README → "Design decisions" |

Task criteria:

| Task | Proven by |
|---|---|
| P4.1 metrics, log correlation | `tests/integration/entrypoints/worker/test_metrics.py::test_worker_metrics_after_a_backfill` (scrapes the worker's own metrics port: `strava_requests_total`, `sync_jobs_total{kind="backfill",status="succeeded"}`), `::test_log_lines_inside_a_job_carry_job_id`; `tests/unit/core/test_metrics.py` (route templates, every metric family exposed, breaker open → `strava_circuit_state` 2); ADR 0010 |
| P4.2 fault suite | `tests/fault/` (`make test-fault`, 11 tests in ~20 s locally; CI `fault` job); each row of the failure-modes table links to its module in `docs/architecture.md` |
| P4.3 load test | `make loadtest` (`scripts/loadtest.sh`, `loadtest/locustfile.py`, `scripts/loadtest_summary.py`); manual `.github/workflows/loadtest.yml`; results and the honest p99 discussion in README |
| P4.4 CI hardening | `pyproject.toml` `[tool.coverage]` `fail_under = 85` enforced by `make coverage` in `make verify`; `make audit`; Dockerfile `HEALTHCHECK` (worker checks its metrics port, compose waits on it); CI jobs `verify` (coverage.xml artifact), `audit`, `fault`, `docker`, `compose`; badge pending a remote (`QUESTIONS.md`) |
| P4.5 README, ADRs, diagrams | README sections (what/why, architecture, failure modes, run, API `curl`, quality gates, load test, design decisions, status); class diagram regenerated from the code; component, deployment, sequence and state diagrams checked against the implementation |
