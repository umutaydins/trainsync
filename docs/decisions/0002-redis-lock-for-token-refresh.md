# 0002 — Redis lock for token refresh

- Status: accepted
- Date: 2026-10-17

## Context
Strava access tokens live six hours and every refresh may return a **new** refresh token, after
which the old one stops working. The API process (OAuth callback) and one or more worker
processes (backfill, incremental sync, webhook processing) all need tokens for the same athlete,
often at the same moment — e.g. a webhook arrives while a backfill page is being fetched. If two
of them refresh concurrently, one of them sends an already-invalidated refresh token, gets an
auth error, or — worse — stores a stale token pair after the other stored the fresh one.

## Decision
`TokenManager` refreshes under a per-athlete Redis lock: `SET token-refresh:{athlete_id} <uuid>
NX PX 15000`, released with a Lua compare-and-delete so only the owner can release it. Inside the
lock it re-reads the tokens and refreshes only if they are still expiring (or, after a 401, still
the token that was rejected). A caller that does not get the lock polls until it is released
(bounded, ~10 s) and then re-reads the tokens from PostgreSQL instead of calling Strava. Refresh
happens proactively 5 minutes before `expires_at`, and once after a 401.

The lock, the token store and the refresher are small protocols, so the refresh logic is unit
tested with in-memory fakes and the race itself with real Redis + PostgreSQL + fake_strava.

## Alternatives considered
- In-process `asyncio.Lock` — only serialises one process; API and workers are separate processes.
- `SELECT … FOR UPDATE` on `oauth_tokens` — works across processes, but holds a DB transaction
  (and a pooled connection) open across an outbound HTTP call with a 10 s read timeout, and the
  waiting side blocks inside the database with no bounded wait.
- Redlock across several Redis nodes — we run one Redis; its failure already stops the queue.

## Consequences
- Redis is on the token path; if it is down, refreshes fail (jobs fail anyway without Redis).
- The 15 s lock TTL must exceed a refresh call; a refresh that retries through several 10 s read
  timeouts can outlive the lock. The double-check inside the lock limits the damage to one failed
  refresh, which surfaces as `StravaAuthError` on that one call.
