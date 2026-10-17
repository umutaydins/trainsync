# 0007 — Fetch current state on every activity event

- Status: accepted
- Date: 2026-10-18

## Context
A Strava activity event only says *that* something changed (`object_id`, `aspect_type`, a
partial `updates` map such as `{"title": …}`), not the activity's new data. Strava may deliver
events more than once and in any order. A create can arrive after its update, or a delete before
the update that preceded it.

## Decision
For `activity create|update`, the worker ignores the payload and calls
`GET /activities/{id}` (high priority, ADR 0004), then upserts the result through the same
idempotent path as the sync jobs. A `404` means the activity no longer exists, so it is soft
deleted. `activity delete` soft-deletes directly (deleting an unknown or already deleted
activity is a no-op). If a fetch succeeds after a delete was processed (the activity exists
again), the fetched state wins and the upsert clears `deleted_at`.

Deauthorization (`athlete update` with `authorized: "false"`) deactivates the athlete and
deletes their tokens and activities in one transaction. That transaction holds the athlete row
lock. Every writer of an athlete's activities (sync pages, webhook upserts) first reads the
athlete `FOR SHARE` and writes nothing if the athlete is inactive, so a page or fetch that was in
flight cannot write deleted data back. Later events for an inactive athlete are marked
processed without fetching.

Event rows move `pending → processing → processed`. `RateLimited`/`CircuitOpen` move them back to
`pending` with a deferred arq `Retry`. Other errors mark them `failed`, which the retry cron
handles (ADR 0008).

## Alternatives considered
- **Apply the payload (`updates.title`)**: it only covers title/type/privacy changes, and
  out-of-order delivery would apply an old title last.
- **Order by `event_time` and drop stale events**: Strava's `event_time` has one-second
  resolution and says nothing about edits made between events. The fetch makes ordering
  irrelevant.
- **Hard delete on `delete` events**: soft delete keeps the row for debugging and costs nothing
  in reads (`deleted_at IS NULL` filter).

## Consequences
- One Strava request per create/update event (duplicates are deduplicated before this point).
  This uses the high-priority budget.
- A new activity that is created and deleted before we process any of its events is never
  stored. Its end state ("not visible") is correct, but there is no soft-deleted row for it.
