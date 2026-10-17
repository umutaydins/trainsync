# 0009 — Keyset pagination over offset

- Status: accepted
- Date: 2026-10-18

## Context
`GET /v1/activities` lists activities newest first. New activities arrive while a client is
paging, from webhooks, the incremental sync or a backfill still running. A long history means
thousands of rows.

## Decision
Order by `(start_date DESC, id DESC)` and page with an opaque cursor: URL-safe base64 of
`{"start_date": iso, "id": int}` from the last row of the page. The next page filters
`(start_date, id) < (:start_date, :id)` (row-value comparison) and fetches `limit + 1` rows.
The extra row tells whether a `next_cursor` exists. A malformed cursor gives `400`.

The service is single-user. Without `athlete_id` it covers all active athletes. With one active
athlete (the normal case) the query uses `athlete_id = :id`, so the
`(athlete_id, start_date DESC)` index provides both the filter and the order. An integration
test asserts this on the `EXPLAIN` plan over 60,000 rows. With several athletes it falls back to
`athlete_id IN (…)`, which is still correct but sorts.

## Alternatives considered
- **`LIMIT/OFFSET`**: an activity inserted above the current position shifts every later page,
  so a row is returned twice (or skipped on delete). Postgres also has to walk and discard
  `offset` rows, so deep pages get slower.
- **Page by `id` only**: ids follow insert order, not training order. A backfill inserts newest
  first and webhooks insert whatever happens, so `id` order is meaningless to a reader.
- **Exposing raw `start_date`/`id` parameters instead of an opaque cursor**: it ties clients to
  the sort key and makes it harder to change later.

## Consequences
- Pages are stable under concurrent inserts and soft deletes. Rows inserted above the cursor
  are simply not in the remaining pages; rows inserted below appear exactly once.
- No "jump to page N" and no total count. A client that needs them can filter by date.
- The cursor encodes the sort key, so changing the order later needs a new cursor version.
