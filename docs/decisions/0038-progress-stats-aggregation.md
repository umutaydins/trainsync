# 0038 — Progress statistics: local-day SQL aggregation, period rules, versioned cache

- Status: accepted
- Date: 2026-10-19

## Context
Progress statistics (P8.10, P8.11) compare a user's training, food and body weight over a
period with the period before. Users live in different time zones (ADR 0035), so "this week"
starts at a different instant for each of them, and a DST change makes a local day 23 or 25
hours long. Three years of data are a few thousand activities and tens of thousands of sets per
user; the all-time and yearly views read all of it. The numbers must change as soon as new data
arrives (a synced activity, a logged set, a meal from the bot).

## Decision
- **Local days in SQL.** A period resolves to inclusive local dates; the query bounds are the
  UTC instants of the local midnights (`zoneinfo`), so the `(user_id, start_date)` indexes still
  serve the range, and rows are grouped by `date(timezone(:tz, start_date))` in Postgres. Date
  columns (food logs, body metrics, check-ins) are already local days. All sums, counts and
  e1RM maxima are computed in Postgres; Python only shapes the result (no N+1, one query per
  block).
- **Periods.** `week`, `month`, `year` are calendar periods *to date* and compare with the same
  number of days at the start of the previous calendar unit (1–19 Oct vs 1–19 Sep; a short
  month clamps). `last_week`, `last_month` are complete units and compare with the unit before.
  `3m`, `6m`, `12m` end today and start the same day N months back (+1 day); `custom` is any
  `from`..`to`; both compare with the same number of days right before. `all` starts at the
  first data of the user and has no previous period. A change is `value - previous` and
  `change / previous` (null when the previous value is 0 or missing).
- **Buckets.** Day up to 31 days, week (ISO, Monday) up to 183 days, month beyond — the
  smallest bucket that still fits a phone-wide chart; the client may ask for another one.
- **Strength.** e1RM is Epley over working sets of at most 10 reps (`STATS_E1RM_MAX_REPS`; the
  training screens keep 12, ADR 0018, because they rank a single lift's sets, not a trend). A PR
  is a set whose e1RM is strictly above every earlier set of the same exercise, computed with a
  window function over the whole history. Adherence counts planned sessions of the *active*
  program (its weekdays, or `days_per_week` per week without them) from the day it was created.
- **Streaks.** The training streak counts ISO weeks with at least one session (a rest day must
  not break a habit); the check-in streak keeps the daily rule of ADR 0020.
- **Cache.** Windows of `STATS_CACHE_MIN_DAYS` (180) or more are cached in Redis under
  `stats:<user>:<data version>:<view>:<parameters>` for `STATS_CACHE_TTL_S`. The data version is
  a row per user in `user_data_versions`, bumped by an `AFTER INSERT OR UPDATE OR DELETE` row
  trigger on every table the statistics read. Every writer — API, bot, sync worker, demo seed,
  a manual `psql` fix — invalidates the cache without knowing it exists; a stale entry is never
  read again and expires on its TTL.
- **Layering.** `stats` reads check-ins, nutrition rules and user settings, so it moves to its
  own layer between `chat` and `admin | users` (import-linter).

## Alternatives considered
- Aggregating in Python over loaded rows — simple, but three years of sets per request is slow
  and memory-hungry; Postgres does it in milliseconds with the indexes.
- A materialised daily rollup table — fastest reads, but every writer would have to keep it in
  step (or a nightly job would make it stale); the live queries are fast enough (< 300 ms for
  three years, tested).
- Invalidating the cache from the write paths — every router, the bot and the sync jobs would
  need the hook, and a forgotten one serves stale numbers; a fingerprint of counts and maxima
  misses edits in place. The trigger catches everything at the cost of one indexed update per
  written row.
- Rolling "last 7 / 30 days" instead of calendar weeks and months — the coach and the user
  talk about "this week" and "last month"; rolling windows are offered as `3m`/`6m`/`12m`.

## Consequences
- A bulk write (backfill page, demo seed) bumps the same version row once per row: cheap, but
  the row is hot inside that transaction; writes for one user serialise on it briefly.
- New tables the statistics read must get the trigger in their migration (a test lists them).
- Month-based previous periods can differ by a day or two in length (31 vs 30 days); the
  response carries both windows so a client can show them.
