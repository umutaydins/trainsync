# 0004 — Two-priority rate budget

- Status: accepted
- Date: 2026-10-18

## Context
Strava allows a fixed number of requests per 15-minute window and per day (by default 200 and
2,000, with separate read limits). Each response reports the limits and current usage in
`X-RateLimit-Limit` / `X-RateLimit-Usage` (and `X-ReadRateLimit-*`). A first backfill of a long
history needs hundreds of requests and can easily take the whole budget. Webhooks keep arriving
in the meantime, and each one needs a `GET /activities/{id}` to fetch the athlete's latest change.
arq has no job priorities (ADR 0003).

## Decision
`RateBudget` keeps the latest snapshot in Redis (`ratelimit:latest`, with the 15-minute window it
was observed in), so the API and every worker see the same numbers. Before every Strava API call
the client asks `allow(priority)`:
- `low` (backfill, incremental sync) is denied once the 15-minute **or** daily ratio reaches
  **80%**; it resumes at the next quarter hour or the next 00:00 UTC. The job marks its run
  `paused` and is deferred to that time.
- `high` (webhook-driven fetches) is allowed until the 15-minute window is actually exhausted
  (or the daily budget is, in which case it waits for midnight).
- A snapshot from an earlier 15-minute window is ignored for the short ratio, because usage
  resets on the quarter hour. The daily ratio still counts if it is from the same UTC day.
- After a 429 the client sets `ratelimit:blocked_until` to the next window reset (midnight if the
  daily budget is exhausted), and both priorities wait. A 429 is never retried in place.

Decisions compare stored timestamps with the injected clock. Redis TTLs only clean up old keys,
which keeps the logic testable with a fake clock.

## Why these choices
- **Fresh data beats backfill progress.** A webhook means the athlete just changed something and
  expects to see it. A backfill that finishes one window later loses nothing.
- **80%.** Leaves about 20% of every window (about 40 of 200 requests) to webhook fetches, which
  is far more than one athlete's activity volume needs. It also leaves headroom for requests
  already in flight when the threshold is crossed, so concurrent low-priority calls don't
  overshoot into 429s.
- **Headers, not constants.** Limits differ per app and Strava can change them; the read limits
  are separate. Reading them from every response also accounts for usage by other processes
  sharing the same app credentials.
- **Wait for the reset on 429.** Retrying inside the window only burns more of a budget that is
  already exhausted, and can get the app flagged.

## Alternatives considered
- Hard-coded limits with a local token bucket: wrong as soon as the limits or another consumer change.
- Separate arq queues per priority: arq has no priorities, and two queues still share one Strava
  budget, so we would need the budget anyway.
- Per-process budget state: each worker would only see its own usage.

## Consequences
- Every Strava call costs one Redis read (and a write per response). That is negligible next to
  the HTTPS round trip.
- Concurrent workers can still slightly overshoot between snapshots. The 20% headroom and the
  429 block absorb this.
- A backfill of a long history spreads over several windows on purpose. Sync status shows it as `paused`.
