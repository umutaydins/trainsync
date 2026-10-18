# 0023 — The Mac as a server: a login LaunchAgent and one control script

- Status: accepted
- Date: 2026-10-18

## Context
Phase 7 runs the production stack on the owner's MacBook (M1, fanless, always on). The stack runs
in Docker Desktop, which is a per-user GUI app: its engine only exists inside a logged-in session.
After a reboot or an update the stack must come back without manual steps, and day-to-day
operations (start, stop, logs, health of the Mac itself) should not need remembering compose flags.

## Decision
- `scripts/mac-prod.sh` is the only entry point: `up` (migrations as a one-shot `migrate` run,
  then `up -d`), `build`, `down`, `status`, `logs`, `restart`, `doctor`, `install-agent`,
  `uninstall-agent`. The image tag is `TRAINSYNC_TAG` from the shell, else `.env.prod`, else the
  git SHA.
- A **LaunchAgent** (`com.trainsync.stack`, `RunAtLoad`, no `KeepAlive`) runs
  `deploy/macos/start-stack.sh` at login: it waits up to 10 minutes for `docker info`, then runs
  `mac-prod.sh up`. Containers then stay up through compose's `restart: unless-stopped`. The plist
  is a template; `install-agent` renders absolute paths into `~/Library/LaunchAgents/`, because
  launchd expands neither `~` nor variables.
- `doctor` checks what makes the Mac fit to serve (env file, Docker running and starting at
  login, no AC sleep, free disk, Tailscale and Funnel, the stack answering, the agent loaded) and
  prints a fix command per failure; backup age and the login-after-reboot setup are warnings.
- Every external command is looked up on `PATH`, so the tests run both scripts against stub
  commands and nothing in CI touches a real Mac.

## Alternatives considered
- A LaunchDaemon (runs at boot, before login) — Docker Desktop's engine does not run without a
  user session, so the daemon would only wait. It would need a headless engine (colima, OrbStack),
  another moving part on a 16 GB machine.
- Only Docker Desktop's "start at login" plus `restart: unless-stopped` — brings back containers
  that were running, but not a stack that was down or never started, and runs no migrations.
- A Makefile instead of a script — the agent and the docs need one stable command; make targets
  call the script where useful (`make doctor`).

## Consequences
- Unattended recovery after a power loss needs a logged-in session: with FileVault on, someone
  must unlock the Mac (planned restarts use `fdesetup authrestart`); automatic login requires
  FileVault off. That trade-off is the owner's and is documented in `docs/operations.md`.
- `scripts/mac-prod.sh down` lasts until the next login unless the agent is uninstalled.
- The scripts stay bash 3.2 compatible (macOS `/bin/bash`) and shellcheck clean (`make shellcheck`).
