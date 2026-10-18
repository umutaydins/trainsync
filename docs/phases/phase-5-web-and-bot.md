# Phase 5 — Web dashboard and Telegram bot

Goal: make the data usable day to day — a small private web dashboard and a Telegram bot that
answers questions and announces new activities — without weakening the backend's guarantees.

## Tasks
1. Read API additions the clients need (activity detail, range summary).
2. `web/`: Next.js (App Router, TypeScript, Tailwind) with a server-side BFF that holds the API key;
   the browser never sees it. Single-user access gate.
3. Dashboard (weekly volume chart, totals by sport), activity list with filters and keyset
   paging, activity detail.
4. Sync status page and "Connect Strava" button; Playwright e2e against the compose stack.
5. Telegram bot process (long polling): `/week`, `/last`, `/stats`, `/status`; chat allowlist.
6. New-activity notifications through a `Notifier` interface (Telegram now, WhatsApp later),
   idempotent per activity.
7. Optional: natural-language questions in the bot using Claude tool use over the read API.

## Acceptance criteria
- `make verify` and `make web-verify` green; CI runs both.
- The API key never reaches the browser (test asserts on built client bundles and responses).
- Dashboard numbers match `GET /v1/stats/weekly` for the same range (e2e).
- Bot replies only to allowlisted chats; a new activity produces exactly one notification even
  if the webhook is delivered twice.
- Compose starts `web` and `bot` alongside the existing services; `make compose-smoke` still passes.

## Evidence

Phase criteria:

| Criterion | Proven by |
|---|---|
| `make verify` and `make web-verify` green | Both pass locally on the merged `phase-5` tree on 2026-10-18: `make verify` (lint, mypy strict, unit + integration tests, branch coverage 97% ≥ 85%) and `make web-verify` (eslint, `tsc`, vitest, `next build`, `check-bundle`). Also green the same day: `make test-fault` (12 tests), `make compose-smoke`, `make web-e2e`, `make audit` and `pnpm audit --prod` (no known vulnerabilities). |
| CI runs both | `.github/workflows/ci.yml` defines a `web` job (`make web-verify`) and an `e2e` job (`make web-e2e`, needs `compose`) next to `verify`, `audit`, `fault`, `docker` and `compose`. **These jobs have not run in CI yet**: the branch has not been pushed. They pass locally (above). A green CI run is pending the owner's push and PR. |
| The API key never reaches the browser (client bundles and responses) | Bundles: `web/scripts/check-bundle.mjs`, run by `make web-verify` after a build with canary values for `TRAINSYNC_API_KEY`, `DASHBOARD_PASSWORD` and `DASHBOARD_SESSION_SECRET`; it fails if any of them appears under `.next/static` or `public/`. Responses: `web/tests/bff.test.ts` ("never echoes the API key in responses", "maps validation errors and 401s without leaking details"); `web/e2e/dashboard.spec.ts` step "the browser never sees the API key" (BFF response and dashboard HTML); `scripts/compose_smoke.sh` (BFF summary must not contain `dev-key-1`). ADR 0011 |
| Dashboard numbers match `GET /v1/stats/weekly` for the same range (e2e) | `web/e2e/dashboard.spec.ts` step "dashboard KPIs equal /v1/stats/summary and the chart equals /v1/stats/weekly": for 2025-03-01 – 2025-12-31 the KPI tiles equal `/v1/stats/summary`, every weekly row (week start, count, distance) equals `/v1/stats/weekly`, and the weekly counts sum to the summary count |
| Bot replies only to allowlisted chats | `tests/unit/test_bot_handlers.py::test_allowlisted_chat_gets_the_reply_others_get_nothing`, `::test_poller_replies_to_allowlisted_updates_only_and_advances_offset` |
| A new activity produces exactly one notification even if the webhook is delivered twice | `tests/integration/test_notifications.py::test_duplicate_webhook_delivery_sends_one_notification`; `tests/fault/test_telegram_down.py::test_telegram_down_then_back_sends_exactly_one_message`. ADR 0012 |
| Compose starts `web` and `bot`; `make compose-smoke` still passes | `docker-compose.yml` services `web` (:3000) and `bot` (metrics :9101, health-checked); `scripts/compose_smoke.sh` waits for every service to be healthy, then checks the web login gate, the BFF (401 without a session, 405 for POST) and key isolation. Passed on 2026-10-18. |

Task criteria:

| Task | Proven by |
|---|---|
| P5.1 read API additions | `tests/integration/test_activities_api.py::test_detail_returns_one_activity_with_optional_raw`, `::test_detail_is_404_for_unknown_soft_deleted_or_inactive`, `::test_detail_requires_api_key`; `tests/integration/test_stats_and_status.py::test_summary_matches_hand_computed_fixture`, `::test_summary_sport_filter`, `::test_summary_of_an_empty_range`; `tests/unit/test_openapi.py::test_docs_openapi_json_is_current`, `::test_every_operation_has_summary_tag_and_examples` |
| P5.2 web scaffold, BFF, access gate | `web/tests/proxy.test.ts` (redirect to `/login`, 401 JSON for BFF calls, forged/expired cookie rejected); `web/tests/login-route.test.ts` (wrong password → 401 and no cookie, right password → signed httpOnly cookie and redirect, no off-site redirect, `Secure` flag); `web/tests/bff.test.ts` (allowlisted GETs only, API key added server-side, errors mapped, 502 when the API is down); `web/scripts/check-bundle.mjs`; `scripts/compose_smoke.sh`. ADR 0011 |
| P5.3 dashboard, activities, detail | `web/tests/format.test.ts` (units, pace for runs, speed for rides); `web/tests/activity-list.test.tsx` ("Load more" appends without duplicates, error state retries with the same cursor, empty state); `web/tests/dashboard-blocks.test.tsx` (totals from `/v1/stats/summary`, empty and error states, the skeleton reserves the chart's height so there is no layout shift); `web/tests/a11y.test.tsx` (axe); `web/tests/api-types.test.ts` (`lib/api-types.ts` matches `docs/openapi.json`) |
| P5.4 sync page, Connect Strava, e2e | `make web-e2e` (`scripts/web_e2e.sh`, `web/e2e/dashboard.spec.ts`: login, Connect Strava through fake OAuth back to `/sync?connected=1`, backfill succeeds, dashboard equals the API, activity list and detail, sync page; screenshots in `docs/img/`); passes locally, CI `e2e` job not run yet (see above). Open redirect: `tests/unit/test_auth.py::test_off_allowlist_return_to_is_ignored`, `::test_return_to_is_ignored_without_an_allowlist`, `::test_callback_with_a_tampered_return_to_is_rejected`, `::test_login_signs_an_allowlisted_return_to_into_the_state`; `tests/integration/test_oauth_flow.py::test_connect_with_return_to_lands_back_on_the_dashboard`. ADR 0015 |
| P5.5 Telegram bot | `tests/unit/test_bot_formatting.py` (numbers, units, empty week); `tests/unit/test_bot_handlers.py` (allowlist with a respx fake Telegram API, `::test_poll_429_is_honoured_without_a_busy_loop` with an injected sleep); `tests/unit/test_bot_telegram.py::test_429_waits_exactly_retry_after_then_sends_once`, `::test_429_until_attempts_run_out_raises_retry_after`; `tests/integration/test_bot_week.py::test_week_numbers_equal_stats_summary` (API in-process). ADR 0013 |
| P5.6 new-activity notifications | `tests/integration/test_notifications.py::test_duplicate_webhook_delivery_sends_one_notification`, `::test_backfill_of_1000_activities_sends_no_notification`, `::test_failed_send_releases_the_claim_and_gives_up_after_max_tries`, `::test_retry_after_from_telegram_sets_the_minimum_deferral`, `::test_unknown_delivery_keeps_the_claim`, `::test_deleted_activity_and_disabled_notifier_send_nothing`; `tests/fault/test_telegram_down.py::test_telegram_down_then_back_sends_exactly_one_message` (`make test-fault`). ADR 0012 |
| P5.7 natural-language questions (optional) | `tests/unit/test_bot_assistant.py` with a scripted fake planner and a respx-stubbed read API: `::test_tool_calls_run_against_the_api_and_the_answer_uses_its_numbers`, `::test_invalid_arguments_are_reported_back_and_not_executed`, `::test_tool_call_limit_is_enforced`, `::test_timeout_is_enforced`, `::test_rate_limited_chat_never_reaches_the_model`, `::test_tool_schemas_are_strict`; `tests/integration/test_assistant_rate_limit.py::test_per_chat_hourly_limit` (Redis). No test calls Anthropic: `tests/conftest.py` points the SDK at `http://anthropic.invalid`. ADR 0014 |
| P5.8 gate | This section; `docs/diagrams.md` (web, bot and notifications in the component and deployment diagrams, `notifications` in the ER diagram, `Notifier` in the class diagram, sequences 11 and 12); README (screenshots from the e2e run, bot commands, Telegram setup, new env vars, ADRs 0011–0015, Status). "CI green on `main`" is **not met yet**: nothing is pushed, so no CI run exists. |
