# 0017 — Client-generated ids for idempotent set logging

- Status: accepted
- Date: 2026-10-18

## Context
Sets are logged from a phone in the gym, often on bad Wi-Fi. A request can reach the server
while its response is lost, and then the client retries it. People also double-tap. If the API
created a set on every `POST`, each retry would store a duplicate, and volume, records and
progression suggestions would all be wrong.

## Decision
- The client makes a UUID for each set **before** the first attempt and logs it with
  `PUT /v1/training/workouts/{workout_id}/sets/{client_id}`. `workout_sets.client_id` is unique.
- The handler upserts with one `INSERT … ON CONFLICT (client_id) DO UPDATE … RETURNING`, so two
  concurrent copies of the same request serialize on the unique index and end up as one row.
  `xmax = 0` in `RETURNING` says whether the row was inserted, so the API answers `201` the first
  time and `200` after that, with the same body when the input is the same.
- The same `PUT` with changed fields is a correction: it updates that set. The body includes
  `completed_at` from the client, so a retry does not move the set in time.
- The conflict update only applies when the stored row is in the same workout. A `client_id` used
  in another workout is `409`, so a client bug cannot move a set between workouts.
- `DELETE …/sets/{client_id}` returns `204` even when the set is already gone, so a retried delete
  does not fail either.
- Starting a workout follows the same pattern: `PUT /v1/training/workouts/{client_id}`
  (`workouts.client_id` is unique, migration 0009) with `INSERT … ON CONFLICT DO NOTHING`. The
  first start wins: a repeat answers `200` with that workout unchanged, whatever its body says,
  so a double tap, a retry after a lost answer, or the check-in reopening the day never makes a
  second workout. The web keeps one id per start button until the start succeeds; the bot uses
  `uuid5("tg:{chat}:{update}:start")` for `/log` and `uuid5("checkin:{date}:workout")` for the
  check-in. The old `POST /workouts` is gone.

## Alternatives considered
- `POST` with an `Idempotency-Key` header and a stored-response table: more moving parts (key
  expiry, stored bodies) for the same result. The set itself is the natural thing to key.
- Deduplicate on (workout, exercise, set_index): a real second set with a reused index, or a
  re-ordered set, would be lost or merged.
- Server ids with "check before insert": racy under concurrent retries unless locked, and the
  client still could not tell whether its lost request went through.

## Consequences
- Offline queuing in the web client (P6.6) is safe: replaying the queue is always correct.
- Clients must keep the id with the pending set until the server confirms it.
- A start repeated with a different body (another program day, a later `started_at`) is
  ignored rather than rejected. A `409` would break the check-in "edit" flow, which re-starts
  the day's workout after the program has moved on to its next day.
