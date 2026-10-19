# 0040 — Sync error codes for people, a rolling heatmap

- Status: accepted
- Date: 2026-10-19

## Context
The UI review found two API shapes that leaked into the screens:

- `/v1/sync/status` returned a failed run's error as stored, `"StravaAuthError: …"`, and the
  web app printed it. A member cannot act on an exception name, and the text is technical detail
  that is not theirs to see.
- `/v1/stats/heatmap` only knew calendar years, so in October the default view was nine months of
  history next to almost three months of empty future days.

## Decision
- Each run in `/v1/sync/status` gets an `error_code`: `strava_auth`, `deauthorized`,
  `strava_unavailable`, `strava_rejected` or `internal`. It is derived when the response is built
  from the stored text's exception name (`modules/sync/errors.py`), so no migration or backfill.
  The web app shows a translated title, a sentence and an action (Reconnect Strava when Strava
  wants a fresh authorization). `error` stays in the response for the owner only; the web app
  folds it into a "Technical details" disclosure.
- `/v1/stats/heatmap` without `year` is the last 365 days up to today; with `year` it is
  1 January to 31 December cut at today. A future year is a 400. The response says which
  (`rolling`, `window`). The year picker goes last 12 months → this year → earlier years.

## Alternatives considered
- Store a code column on `sync_runs`: cleaner long term, but a migration and a backfill of old
  rows for a value that the stored text already determines.
- Map the exception names in the web app: puts knowledge of backend exception classes in the
  frontend and still sends the raw text to every user.
- A rolling heatmap built in the web app from two calendar-year requests: two calls and a merge
  for what is one SQL range.

## Consequences
- Renaming a Strava exception class changes its code to `internal` unless `errors.py` follows
  (its unit test lists every mapped class).
- New failure kinds need a code, an `en` and a `tr` message.
