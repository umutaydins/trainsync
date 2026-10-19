# 0033 — Modular-monolith layout with enforced layers

- Status: accepted
- Date: 2026-10-19

## Context
The package grew by technical kind (`api/`, `db/`, `bot/`, `notify/`), so one feature was spread
over five folders, `db/models.py` held every table, and the worker's senders imported the bot
process (`notify/*` → `bot/*`). Phase 8 makes the app multi-user, which touches every domain;
without clear module boundaries each change would cut across the whole tree. The repository is
also a public portfolio and should read like a codebase a team could work in.

## Decision
- `src/trainsync` has four layers, top to bottom, checked by import-linter in `make lint` (and so
  in CI):
  - `entrypoints/` — thin composition roots: `api` (app factory, middleware, health, router
    registry), `worker` (arq settings, cron registry), `bot` (polling, dispatcher), `demo`. They
    are independent of each other.
  - `modules/<domain>/` — one package per domain (`activities`, `strava`, `sync`, `stats`,
    `training`, `checkin`, `nutrition`, `coach`, `chat`, `notifications`), with the same file
    names where they apply: `router.py`, `schemas.py`, `repository.py`, `models.py`, `tasks.py`.
    Modules depend downward in a fixed order (notifications → chat → coach | checkin | nutrition
    | stats | sync → training → activities → strava); `models.py` (tables) may be imported by
    any module. `modules/models.py` imports every model module so `Base.metadata` is complete.
  - `integrations/` — outbound clients only (Strava, Telegram, Anthropic, Open Food Facts); they
    never import modules.
  - `core/` — settings, DB engine/session and ORM base, logging, metrics, crypto, clock, errors,
    FastAPI dependencies, the job queue.
  - `ops/` stays standard-library only (it also runs in the backup image): a forbidden contract.
- `modules/chat` holds the Telegram conversation (command features, parsing, formatting, the
  read-API client). The bot is an API client by design (ADR 0012, 0013); putting the
  conversation below the entrypoints lets the worker's senders reuse its formatting without
  importing the bot process. Message packs live in `modules/coach/packs`.
- Tests mirror the source tree: `tests/{unit,integration}/<layer>/<module>/`; `tests/fault`
  stays a flat set of end-to-end scenarios.
- Web: `web/src/app` (routes only), `web/src/features/<domain>` (components, API calls, types,
  hooks), `web/src/lib` (BFF client, generated API types, session, CSRF, config, formatting),
  `web/src/components/ui` (primitives), `web/src/styles`. ESLint `no-restricted-imports` rules
  keep `lib` and `components/ui` from reaching up and `features` from importing routes.
- The move was done with `git mv`, so `git log --follow` keeps each file's history.

## Alternatives considered
- Keep the technical layout and add folders inside it — the bot/worker cycle and the god files
  stay.
- Split into separate packages or services per domain — one person, one database, one deploy;
  the cost buys nothing yet. A modular monolith keeps that door open.
- A strict "only through `service.py`" rule between modules — the existing modules talk through
  their schemas and repositories; forcing a service file into each would add pass-through code.
  The layer order already prevents cycles; a module's public surface is documented in its
  `__init__.py` docstring.
- `eslint-plugin-boundaries` for the web — `no-restricted-imports` is built in and covers the
  three rules we need.

## Consequences
- New code has an obvious home, and a wrong-way import fails `make lint`.
- Logger names follow the module paths (`trainsync.modules.sync.backfill`), so log queries that
  filter by logger need the new names.
- `python -m trainsync.entrypoints.bot`, `arq trainsync.entrypoints.worker.settings.WorkerSettings`
  and `uvicorn trainsync.entrypoints.api.app:create_app` replace the old commands (compose files
  and the Dockerfile are updated).
- Two small code moves were needed for the layers: the sync-health reads moved into
  `modules/sync/status_repository.py`, and deauthorization (deactivate, drop tokens and
  activities) into `modules/sync/deauthorization.py`.
