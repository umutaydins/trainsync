# 0019 — Energy-balance estimates and the Open Food Facts lookup

- Status: accepted
- Date: 2026-10-18

## Context
P6.4 shows food intake next to an estimate of what I burn, and lets me find foods by barcode or
name without typing in nutrition labels. Two choices need writing down:

1. **How expenditure is estimated.** Every input has gaps: body weight is entered only now and
   then, Strava's `calories` exists only on detailed activities (webhook fetches, not list pages),
   many activities (strength, walks without HR) have no energy at all, and the timezone of a "day"
   is not obvious.
2. **How a third-party food database is used.** Open Food Facts (OFF) is free and keyless but
   slow at times, rate-limits heavy users, and its data quality varies per product.

## Decision
**Estimates, with every gap visible.**
- BMR by Mifflin–St Jeor from the profile (sex, birth year, height) and the latest
  `body_metrics.weight_kg` on or before the day. Age = the day's year − birth year (only the year
  is stored). No profile or no weight → BMR, baseline, expenditure and balance are `null` and
  `estimate_unavailable_reason` says why. No default weight or height is assumed.
- Everyday baseline = BMR × 1.2 / 1.375 / 1.55 (sedentary / light / moderate). The multiplier
  covers daily life only; exercise is added from activities, so it is never counted twice
  (classic "activity factors" include exercise; ours explicitly do not).
- Exercise energy per synced activity: `raw.calories` when > 0 (Strava's own estimate; 0 means it
  had nothing to base it on, so it is treated as missing), else for `sport_type` containing
  `Ride` `raw.kilojoules` taken as kcal (mechanical work at ~24 % gross efficiency makes
  1 kJ of work ≈ 1 kcal burned), else **unknown**. Unknown activities are listed with
  `kcal: null` and counted; the day reports `exercise_complete` and `balance_complete = false`.
  We never fall back to MET tables or HR formulas: a number that looks exact but is invented is
  worse than an honest "unknown".
- Balance = intake − (baseline + known exercise). Days are UTC days, like the rest of the read
  API (`start_date`, not `start_date_local`).
- `Decimal` arithmetic, rounded to 0.1 kcal / g only at the end, so the hand-computed fixture
  (`tests/fixtures/nutrition_energy.json`) matches exactly.
- A `kcal_target` below BMR is stored as entered with a neutral `warning`. The API never proposes
  targets or deficits.

**Open Food Facts as a lookup that fills a local cache.**
- One module (`nutrition/off_client.py`) calls OFF: product by barcode (`/api/v2/product/{code}`)
  and name search (`/cgi/search.pl`), with a custom User-Agent as OFF asks, the process's shared
  `httpx.AsyncClient` and a 3 s whole-request timeout. No retries: a person is waiting.
- Usable products (valid barcode, a name, kcal per 100 g from `energy-kcal_100g` or `energy_100g`
  kJ / 4.184, within 0–1000) are upserted into `foods` by barcode with `source=openfoodfacts`.
  Out-of-range macros are stored as unknown (`null`). A known barcode is answered locally without
  asking OFF again (`remote: "cached"`).
- Editing a cached product turns it into `source=manual`; the upsert only updates rows that are
  still `openfoodfacts`, so a correction is never overwritten. `favorite` is never touched by the
  cache.
- Graceful degradation: timeout, network error, 5xx/429 or an unreadable body → the endpoint still
  answers 200 with local matches and `remote: "unavailable"`. `OPENFOODFACTS_ENABLED=false` gives
  `remote: "disabled"` and never calls out. The remote call runs outside any DB session.
- Tests never reach OFF: `OPENFOODFACTS_BASE_URL` points at `http://openfoodfacts.invalid` in the
  test settings and respx fakes it.

## Alternatives considered
- **Guess unknown exercise from MET × duration × weight** — plausible-looking numbers with large,
  invisible error; the flag keeps the UI honest instead.
- **Activity multiplier including exercise (TDEE-style 1.2–1.9)** — double counts every synced
  activity.
- **Local day boundaries from `start_date_local`** — Strava's local time has no offset we store per
  activity, and every other endpoint uses UTC days; one convention everywhere is simpler. A late
  evening session in UTC+3 can land on the next day; documented.
- **Proxy every search to OFF without caching** — slow, fragile, and a logged food would depend on
  a third party being up when the summary is read.
- **USDA FoodData Central** — needs an API key and has few packaged EU/TR products with barcodes.
- **Snapshot kcal/macros into each food log** — would freeze history against later corrections;
  not needed for one user, so logs reference the food's current values (a correction updates past
  days too).

## Consequences
- The summary carries more fields (`*_complete`, `*_unknown_count`, `estimate_unavailable_reason`)
  that the web and the bot must show rather than hide.
- Activities synced only from list pages (backfill) usually lack `calories`; until a webhook
  fetches the detailed activity, runs show as unknown and rides fall back to kilojoules.
- OFF data is cached forever; a bad product can be fixed by editing it (becomes `manual`).
- Watch OFF's usage policy (search is rate-limited per IP); lookups are user-triggered only, never
  from jobs.
