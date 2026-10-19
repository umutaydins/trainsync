# 0037 — Strava per user, fair sync, account deletion and data export

- Status: accepted
- Date: 2026-10-19

## Context
One Strava application serves every user. Its rate limit (100 requests / 15 min, 1,000 / day by
default) is shared, and a first backfill of a long history can take thousands of calls. Users
must be able to leave and take their data with them (KVKK / GDPR).

## Decision
- **Binding**: `GET /auth/strava/login` needs a signed-in user; the signed OAuth state carries
  the user id (and the return URL, ADR 0015). The callback binds the athlete to that user. A
  Strava athlete already bound to another user is refused (409, nothing written); a user has at
  most one active athlete. Webhooks route `owner_id` → athlete → user.
- **Fair scheduling**: a backfill job stores its cursor and stops after `BACKFILL_PAGES_PER_JOB`
  pages, then re-enqueues itself with a short defer, so jobs of several athletes interleave in
  the queue; incremental syncs and webhook fetches keep their higher priority in the shared
  budget (ADR 0004), so one big backfill never delays other athletes' fresh activities.
- **Deletion**: `DELETE /v1/me` (password re-entry) sets `deleted_at`, revokes all sessions and
  unlinks Telegram at once, then enqueues `purge_user`, which calls Strava's deauthorize
  endpoint (best effort) and deletes every row of the user (the `ON DELETE CASCADE` from
  `users`). The owner account cannot be deleted through the API.
- **Export**: `GET /v1/me/export` returns one JSON document with every row the user owns
  (profile, settings, Strava athlete without tokens, activities, programs, workouts, sets,
  check-ins, body metrics, nutrition profile, food logs, own foods and exercises).
- **Capacity**: new Strava apps allow one connected athlete; the owner must request a capacity
  increase from Strava before other users can connect (`docs/strava-setup.md`).

## Alternatives considered
- Per-user rate budgets — Strava limits the app, not the athlete; a per-user split would waste
  budget while others are idle.
- Hard delete at once — a soft delete answers the request immediately and the purge can retry a
  failed Strava call without blocking the user.

## Consequences
- A first backfill takes longer in wall time when others are syncing; nobody's fresh data waits.
- A deleted user's email can register again after the purge.
