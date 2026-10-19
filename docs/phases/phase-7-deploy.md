# Phase 7 — Deploy: backend on the MacBook, web on Vercel

Goal: run trainsync for real — backend on the always-on MacBook behind Tailscale Funnel, web on
Vercel (`*.vercel.app`), real Strava connected — plus a separate public demo with fake data, all
portable to a VPS/Oracle later without code changes.

Runs right after Phase 6 (before body composition, now Phase 9) so the Apple Health Shortcut
and real Strava webhooks have a public URL from day one.

## How this phase is run
Interactive, not unattended: some steps need the owner (Tailscale login, secrets in `.env.prod`,
Vercel env, Strava app, `sudo pmset`, the reboot test). When a task reaches such a step, stop and
ask with the exact command/value needed; never fake evidence for a manual check. Every manual
check is recorded in `docs/operations.md` → "Owner checks" with date and output.

## Tasks
1. Production compose (`compose.prod.yml`) with secrets, restricted ports and a public-route gateway.
2. macOS service management: start on login/boot, one control script, sleep checks.
3. Public HTTPS via Tailscale Funnel (real on 443, demo on 8443); only allowlisted routes exposed.
4. Nightly Postgres backups with retention and a tested restore.
5. Deploy and rollback with one command; migrations as a separate step; smoke test.
6. Vercel project for `web/`, env and CSRF/origin settings; preview deploys use the demo backend.
7. Real Strava app, OAuth callback and webhook subscription management.
8. Uptime monitoring and alerts to Telegram from outside the Mac.
9. Public demo stack (fake data, read-only) linked from the README.

## Acceptance criteria
- After a Mac reboot everything is back without manual steps (documented test procedure + script check).
- Only allowlisted paths are reachable through Funnel; `/metrics`, DB and Redis are not (scripted check).
- Restore from last night's backup into a scratch DB passes a row-count check (scripted).
- Vercel production talks to the real backend; previews to the demo backend; CSRF passes on the Vercel origin.
- The demo rejects every write (tests) and contains no personal data.

## Evidence

Everything the repo can prove is proven by a test or a script that runs in CI. The checks that
need the owner's Mac, Tailscale, Vercel or Strava account are listed in
[operations.md → Owner checks](../operations.md#owner-checks) and stay **PENDING** until the
owner runs them and pastes the output; none is filled in here.

Phase criteria:

| Criterion | Proven by | Owner check |
|---|---|---|
| After a reboot everything is back without manual steps | `tests/unit/scripts/test_mac_prod.py` (stubbed commands): `doctor` reports every failure with a fix (`::test_doctor_reports_each_failure_with_a_fix`), `::test_start_stack_waits_for_docker_then_starts_the_stack`, `::test_install_agent_renders_absolute_paths_and_loads_it`; `tests/unit/scripts/test_deploy.py::test_mac_prod_starts_the_tag_of_the_last_deploy`; `make shellcheck` (CI job). Procedure: operations.md → Reboot test procedure | **PENDING**: Docker AutoStart, `pmset`, `install-agent`, `doctor`, the reboot test itself |
| Only allowlisted paths reachable through Funnel; `/metrics`, DB, Redis are not | `make prod-check` (CI job `prod-check`): Postgres/Redis on an internal network with no ports, only the gateway published on 127.0.0.1, curl matrix from `deploy/gateway/routes.toml` (forwarded vs 404), body limit, `/auth` rate limit, headers; `tests/unit/scripts/test_gateway_routes.py`; `scripts/public_check.py` + `tests/unit/scripts/test_public_check.py` for the real URL | **PENDING**: `funnel.sh on`, `make public-check URL=…`, scheduled `public-check.yml` |
| Restore from last night's backup passes a row-count check | `make restore-check-ci` (CI job `restore-check`): a seeded DB's encrypted backup restores with matching counts; truncated, altered, wrong-key, count-mismatch and missing-sidecar backups fail; the loop and retention run in the image. `tests/unit/ops/test_backup_retention.py`, `tests/unit/ops/test_backup_cli.py` | **PENDING**: age key, first `make backup-now`, `make restore-check` on the real backup |
| Vercel production → real backend; previews → demo; CSRF passes on the Vercel origin | `web/tests/origins.test.ts` (this deployment's exact Vercel URLs accepted, other projects/lookalikes/http refused), `web/tests/backend-status.test.tsx` (offline backend → "Backend unreachable"), `docs/deploy-vercel.md` | **PENDING**: Vercel project + env, production shows real data, preview shows the demo, a write on Vercel passes CSRF |
| The demo rejects every write and holds no personal data | `tests/unit/entrypoints/api/test_demo_mode.py::test_every_write_is_403_in_demo_mode` (operations generated from `app.openapi()`, so a new write route is covered automatically), `::test_reads_pass_the_guard`; `tests/unit/entrypoints/demo/test_demo_seed.py` (seed source: pure imports, no I/O, every text from module constants, deterministic); `make demo-check` (CI job `demo-check`) | **PENDING**: demo stack on the Mac, `funnel.sh on all`, README link |

Task criteria:

| Task | Proven by |
|---|---|
| P7.1 prod compose + gateway | `make prod-check` (CI); `tests/unit/core/test_settings_fail_fast.py` (missing secret → exits naming it, never the value); `tests/unit/scripts/test_gateway_routes.py`; ADR 0022 |
| P7.2 macOS service | `tests/unit/scripts/test_mac_prod.py`; `make shellcheck` (CI); ADR 0023; reboot test PENDING |
| P7.3 Funnel | `tests/unit/scripts/test_funnel.py`, `tests/unit/scripts/test_public_check.py`; `.github/workflows/public-check.yml`; ADR 0025; real run PENDING |
| P7.4 backups | `make restore-check-ci` (CI); `tests/unit/ops/test_backup_retention.py`; ADR 0024; real backup PENDING |
| P7.5 deploy/rollback | `tests/unit/scripts/test_deploy.py::test_smoke_failure_rolls_back_automatically`, `::test_rollback_downgrades_reversible_migrations_before_starting_the_old_image`, `::test_rollback_across_a_non_reversible_migration_refuses_and_prints_the_restore`, `::test_deploy_refuses_before_touching_anything`; `tests/unit/migrations/test_migration_reversibility.py`; every migration steps down and up in `tests/integration/migrations/test_migrations.py`; ADR 0026; first real deploy PENDING |
| P7.6 Vercel | `web/tests/origins.test.ts`, `web/tests/backend-status.test.tsx`; `web/vercel.json`; `docs/deploy-vercel.md`; deployment PENDING |
| P7.7 real Strava | `tests/unit/scripts/test_strava_subscription.py` (create/view/delete and their errors against respx); `docs/strava-setup.md`; real connection PENDING |
| P7.8 uptime + alerts | `tests/unit/ops/test_uptime.py` (down, still down, recovered, flapping), `tests/unit/modules/notifications/test_stack_alerts.py`, `tests/integration/modules/notifications/test_stack_alerts.py`; `.github/workflows/uptime.yml`; ADR 0027; repo secrets + drills PENDING |
| P7.9 demo | `tests/unit/entrypoints/api/test_demo_mode.py`, `tests/unit/entrypoints/demo/test_demo_seed.py`, `tests/integration/entrypoints/demo/test_demo_reset.py`, `make demo-check` (CI); ADR 0028 |
| P7.10 gate | This section; operations.md (start/stop, reboot, deploy, rollback, backup/restore, Funnel, alerts, demo, Strava, rotating secrets, owner checks); ADR 0029 (portability); diagrams 21–25; README |

All automated gates ran green on the merged `phase-7` tree on 2026-10-18: `make verify`,
`make shellcheck`, `make web-verify`, `make prod-check`, `make demo-check`, `make restore-check-ci`,
`make compose-smoke`, `make web-e2e`. None of the new CI jobs has run on GitHub yet (nothing is
pushed).

**Phase 7 is not ticked in README Status**: its acceptance criteria include the reboot test, the
public check against the real Funnel URL, Vercel production and the real Strava connection,
which only the owner can perform (the phase's own rule: "never fake evidence for a manual
check"). Tick it once the PENDING owner checks are recorded.
