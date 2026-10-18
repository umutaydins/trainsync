# Phase 7 — Deploy: backend on the MacBook, web on Vercel

Goal: run trainsync for real — backend on the always-on MacBook behind Tailscale Funnel, web on
Vercel (`*.vercel.app`), real Strava connected — plus a separate public demo with fake data, all
portable to a VPS/Oracle later without code changes.

Runs right after Phase 6 (before body composition, now Phase 8) so the Apple Health Shortcut
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
