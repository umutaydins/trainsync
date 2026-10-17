# 0005 — Per-process circuit breaker

- Status: accepted
- Date: 2026-10-18

## Context
When Strava has an outage, each logical call already costs up to 4 attempts with backoff
(about 15 s worst case). Without a breaker, every queued job keeps trying, which adds load to a
struggling API, uses up our rate budget for nothing, and makes jobs fail instead of waiting.
We run one API process and a few worker processes. Each has one `StravaClient` (one shared
`httpx.AsyncClient`).

## Decision
Each process has one in-memory `CircuitBreaker` (`strava/breaker.py`), owned by its `StravaClient`
and wrapped around every logical API call:
- **Failures** are only `StravaUnavailable`: 5xx, timeouts or network errors after the client's
  retries are exhausted. 4xx and 429 count as **successes**, because Strava answered. A 429 is
  handled by the rate budget (ADR 0004). Errors that say nothing about Strava (cancellation, a
  database error while loading a token) leave the state unchanged.
- `closed → open` after 5 consecutive failures (`STRAVA_BREAKER_FAILURE_THRESHOLD`).
  `open → half_open` after 30 s (`STRAVA_BREAKER_COOLDOWN_S`). In `half_open`, exactly one probe
  goes through, guarded by an `asyncio.Lock`. Every other call gets `CircuitOpen` immediately.
  The probe's outcome closes the circuit or reopens it for another cooldown. Calls that started
  before the circuit opened do not change it when they finish late.
- The breaker check runs **after** the rate-budget check, so a budget denial is never counted as
  an answer from Strava.
- Sync jobs map `CircuitOpen` to a `paused` run and an arq `Retry` that defers to `retry_at` plus
  up to 1 s of jitter. A `StravaUnavailable` that hits a job while the circuit is still closed is
  handled the same way, deferred by 30 s. A transient outage pauses a job and never fails it.
  This is also what makes the breaker's failure count matter: the job comes back, and the
  breaker decides whether its next call goes out.
- `StravaClient.breaker_state` exposes the state for metrics; a listener publishes every
  transition for the sync status endpoint.

## Why per process, not shared in Redis
- **The signal is local anyway.** Every process talks to the same Strava over a similar network
  path, so each one sees an outage within a few calls. With 5 failures per process and a handful
  of processes, a shared breaker would save a few dozen requests per outage. That doesn't justify
  extra machinery.
- **It works when Redis is in trouble.** A shared breaker adds a Redis round trip, and a new
  failure mode, to every call. It also needs an atomic "one probe in the whole fleet" lease
  (Lua script or `SET NX PX`) with expiry handling for a probe holder that dies.
- **Simple to test.** It is a pure state machine with an injected clock and no I/O. Every
  transition is unit-tested without containers.

## Alternatives considered
- **Shared Redis breaker**: see above. Worth revisiting if we scale to many worker processes.
- **Counting individual HTTP attempts instead of logical calls**: retries already absorb isolated
  errors. Counting attempts would open the circuit on a single slow minute.
- **Re-enqueueing a new job instead of arq `Retry`**: the backfill job id `backfill:{athlete_id}`
  is still held by the running job, so a fresh enqueue with the same id is dropped. `Retry` keeps
  the id and the arguments. arq counts it as a try, so `SYNC_MAX_TRIES` is set high (1000) and
  deferrals never exhaust it.
- **Failing the job on `StravaUnavailable`**: an outage would turn into failed runs that need a
  manual or cron-driven restart, and the circuit would never matter to the job.

## Consequences
- During an outage each process sends at most `threshold × 4` HTTP attempts, then one probe per
  cooldown.
- The API process and every worker open and close independently. Each process publishes its
  transitions to Redis (`breaker:{process}`, expiring), and `GET /v1/sync/status` reports every
  process plus the worst state. Publishing is best effort and never fails a Strava call.
- The jitter on deferrals spreads the jobs that were waiting, so they don't all hit Strava in the
  same second when it recovers.
