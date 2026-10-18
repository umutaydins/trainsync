# 0028 — Public demo: read-only by middleware, synthetic seed as code

- Status: accepted
- Date: 2026-10-18

## Context
Recruiters should be able to click a link in the README and explore a realistic dashboard
(P7.9). The real backend holds personal training, nutrition and body data and must never be
that link. The demo has to look alive (the dashboard's default ranges show the last weeks), must
not let a visitor change or fill it, must not run anything that reaches Strava, Telegram or Open
Food Facts, and must not drift from the real code (it is the same image).

## Decision
- **A separate stack**, `compose.demo.yml`: project `trainsync-demo`, own volumes and networks,
  Postgres/Redis/fake_strava internal with no ports, the same gateway image and `routes.toml` as
  production on `127.0.0.1:8081` (Funnel :8443). No bot, no backups. Strava URLs point at
  fake_strava on the internal network, Open Food Facts is off.
- **`DEMO_MODE=true` blocks writes in one ASGI middleware** (`DemoReadOnlyMiddleware`), before
  routing: every method except GET/HEAD/OPTIONS, plus everything under `/auth/strava/` (the
  OAuth callback writes on a GET), answers `403 {"detail": "This is a read-only demo."}` with
  `X-Trainsync-Demo: read-only`. The web BFF shows that message instead of its generic
  "not authorized" for a 403 carrying the header. This also refuses
  `POST /v1/training/programs/generate`, which only previews — one simple rule beats a list of
  exceptions.
- **The test is generated from `app.openapi()`**: every operation the rule calls a write must be
  the demo 403 in demo mode and not a 403 without it; every other operation must pass the guard.
  A new write route is covered without editing the test.
- **The seed is code** (`trainsync.demo.seed`): one `random.Random(7)`, constants for foods,
  program, notes and reasons, dates relative to an injected clock. Twelve weeks before today:
  ~70 Strava-shaped activities (runs, rides, walks, hikes, and a WeightTraining activity per
  gym session), an active 4-day upper/lower program with ~40 workouts and ~550 sets under double
  progression, a check-in for every day (done / partial / skipped / rest / sick), 15 generic
  foods with ~700 food logs, body weight trending from 82.4 to 79.8 kg, and a nutrition profile.
  The athlete has no name. A test parses the module: only pure imports, no file, network,
  environment or `now()` calls, no e-mail/URL/phone-shaped strings, and every text value in
  the built dataset comes from the module's constants.
- **Reset = wipe + seed in one transaction**, written through the ORM and the activity
  repository, never over HTTP. `python -m trainsync.demo reset` refuses unless `DEMO_MODE` is
  on, so it cannot wipe a real database. The stack runs it once on `up` (one-shot `seed`
  service) and the demo worker (`trainsync.demo.worker.DemoWorkerSettings`, the reset cron only;
  no sync, webhooks, notifications or check-in prompts) runs it nightly at 03:00 UTC, which also
  slides the twelve weeks forward to the new day.
- **No stored secrets**: `python -m trainsync.demo exec CMD` starts each process with a fresh
  random Fernet key and OAuth-state key (the demo stores no tokens and signs no state); the
  remaining values are labelled `demo-public-…`; only `DEMO_API_KEY` comes from the git-ignored
  `.env.demo`.
- `make demo-check` (and a CI job) renders the config, starts the stack under a check project and
  port, and through the gateway asserts seeded reads, five kinds of writes refused, `/metrics`
  404 and the in-stack reset.

## Alternatives considered
- A dependency on every write route — must be remembered for each new route; the middleware is
  deny-by-default and the generated test proves the coverage.
- A read-only Postgres role for the API — the API would fail with 500s deep in a handler instead of
  a friendly 403, and the webhook intake and other writes would still need special-casing.
- Seeding over the HTTP API or through fake_strava + a real backfill — needs writes to be open
  during seeding, and fake_strava's in-memory tokens do not survive a restart, so the incremental
  sync would fail and the sync page would show errors.
- A sanitized copy of the real database — "no personal data" would depend on a scrubbing step
  being complete forever; generated data cannot leak anything.

## Consequences
- The demo dashboard's write buttons show "This is a read-only demo." — expected, documented in
  the README.
- A GET route that writes would not be caught by the method rule; it must be added to
  `WRITE_PATH_PREFIXES` (today only the OAuth callback does this).
- Phase 8 extends `seed.py` with body measurements and proposals; the source test keeps it
  synthetic.
- The demo stack costs ~1.2 GB of memory limits on the Mac next to production.
