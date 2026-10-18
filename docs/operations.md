# Operations — the production backend on the MacBook

How the real backend runs on the always-on MacBook (Phase 7): starting and stopping it, what
happens on a reboot, where the logs are, how to update it, and the manual checks only the owner
can perform.

## Overview

- The stack is `compose.prod.yml` (P7.1): Postgres, Redis, migrate (one-shot), api, worker, bot
  and the gateway. Only the gateway publishes a port, on `127.0.0.1:8080`, and it forwards only the
  routes in `deploy/gateway/routes.toml` (ADR 0022).
- Secrets live in `.env.prod` at the repo root (git-ignored, `chmod 600`; template
  `.env.prod.example`).
- `scripts/mac-prod.sh` is the one control script. It always runs
  `docker compose --env-file .env.prod -f compose.prod.yml …`.
- The LaunchAgent `com.trainsync.stack` (`deploy/macos/`) starts the stack at login; the
  containers' `restart: unless-stopped` keeps them running afterwards (ADR 0023).
- Tailscale Funnel makes the gateway public over HTTPS (P7.3).

## Start, stop, status

```
scripts/mac-prod.sh up                 # migrations (one-shot), then the stack in the background
scripts/mac-prod.sh status             # containers and health
scripts/mac-prod.sh logs [service]     # follow logs: api, worker, bot, gateway, postgres, redis
scripts/mac-prod.sh restart [service]  # restart everything, or one service
scripts/mac-prod.sh down               # stop (volumes, i.e. the data, are kept)
scripts/mac-prod.sh build              # build the images for the current tag
scripts/mac-prod.sh doctor             # is the Mac fit to serve? (also: make doctor)
scripts/mac-prod.sh install-agent      # start the stack at every login
scripts/mac-prod.sh uninstall-agent    # stop doing that (the running stack is untouched)
```

Image tag: `TRAINSYNC_TAG` from the shell, else from `.env.prod`, else the current git SHA
(12 characters). Leave it empty in `.env.prod` so the checked-out commit decides.

`doctor` checks, and prints the fix command for every failure (exit 1 if any fails):

| Check | Fix it prints |
| --- | --- |
| `.env.prod` present and private | `cp .env.prod.example .env.prod && chmod 600 .env.prod` |
| Docker is running | `open -a Docker` |
| Docker Desktop starts at login | Settings → General → "Start Docker Desktop when you sign in" |
| No system or disk sleep on power (`pmset -g custom`, AC) | `sudo pmset -c sleep 0 disksleep 0` |
| At least `MIN_FREE_GB` (10) GB free | `docker system prune` |
| Tailscale connected | `open -a Tailscale` / `tailscale up` |
| Funnel forwards to the gateway on `127.0.0.1:8080` | `scripts/funnel.sh on` |
| The stack answers `http://127.0.0.1:8080/health/ready` | `scripts/mac-prod.sh up` |
| LaunchAgent installed and loaded | `scripts/mac-prod.sh install-agent` |

Warnings (printed with a fix, but `doctor` still passes):

- FileVault on, or automatic login off: after an unplanned reboot nothing starts until someone
  logs in (see Reboot below).
- No backup in `BACKUP_DIR`, or the newest `trainsync-*.dump.age` is older than 36 h (P7.4).

Display sleep is fine (the screen may turn off). Closing the lid sleeps a MacBook regardless of
`pmset` unless an external display is attached: keep the lid open.

## Reboot

The LaunchAgent runs at login, so a reboot brings the stack back only once a user session exists:

- **FileVault on** (macOS default): after a reboot the Mac stops at the FileVault unlock screen.
  Planned restarts skip it with `sudo fdesetup authrestart` (unlocks once, then logs in
  automatically). After a power loss someone has to type the password; the uptime monitor
  (P7.8) alerts.
- **FileVault off + automatic login on**: the session, and with it Docker Desktop and the stack,
  comes back without anyone. This trades disk encryption at rest for unattended recovery; it is
  the owner's decision and is not made by any script here.

### Reboot test procedure

1. `scripts/mac-prod.sh doctor` — no FAIL lines.
2. Note the time: `date`.
3. Restart: Apple menu → Restart, or `sudo fdesetup authrestart` with FileVault on.
4. After login touch nothing for 5 minutes (Docker Desktop starts, the agent waits for it, then
   runs `scripts/mac-prod.sh up`).
5. Collect the evidence and paste it into the "Owner checks" table:
   ```
   date
   tail -n 20 ~/Library/Logs/trainsync/stack.log
   scripts/mac-prod.sh status
   curl -fsS http://127.0.0.1:8080/health/ready
   scripts/mac-prod.sh doctor
   ```
   `stack.log` must show `start-stack: Docker is up after …` and `start-stack: stack started`
   with a time after step 2; every service must be `running` / `healthy`.

## Logs

| What | Where |
| --- | --- |
| LaunchAgent (wait for Docker, `up` at login) | `~/Library/Logs/trainsync/stack.log` |
| Containers (JSON lines, structlog) | `scripts/mac-prod.sh logs [service]` |
| Gateway access log (JSON) | `scripts/mac-prod.sh logs gateway` |
| Docker Desktop | `~/Library/Containers/com.docker.docker/Data/log/` |

`stack.log` is appended to on every login and is small; delete it whenever you like.

## Updating

Until `make deploy` (P7.5) exists:

```
git switch main && git pull --ff-only
scripts/mac-prod.sh build      # images tagged with the new git SHA
scripts/mac-prod.sh up         # migrations first, then recreate the changed containers
scripts/mac-prod.sh doctor
```

Rollback: `git switch --detach <previous sha>` and the same two commands (the old images are
still there, so `build` is quick). A migration that is not backwards compatible needs a restore
(Backups and restore) instead.

## Stopping for a while

`scripts/mac-prod.sh down` stops the stack; it comes back at the next login. To keep it down
across logins, also run `scripts/mac-prod.sh uninstall-agent` (and `install-agent` later).

## Funnel (public HTTPS)

Tailscale Funnel gives the Mac a public HTTPS name without a domain or open router ports:
`https://<mac>.<tailnet>.ts.net`. TLS terminates on the Mac (Tailscale fetches a Let's Encrypt
certificate for the ts.net name); Funnel forwards plain HTTP to the gateway, which serves only the
allowlisted routes (ADR 0022, ADR 0025).

```
scripts/funnel.sh on            # https://<host>/      -> gateway 127.0.0.1:8080 (real)
scripts/funnel.sh on demo       # https://<host>:8443/ -> demo gateway 127.0.0.1:8081 (P7.9)
scripts/funnel.sh on all        # both
scripts/funnel.sh status        # Funnel config, public URLs, the values for Strava and Vercel
scripts/funnel.sh off [real|demo|all]
make public-check URL=https://<host>.<tailnet>.ts.net
```

The Funnel config is stored by tailscaled (`--bg`) and survives reboots and Tailscale restarts.

One-time prerequisites (Tailscale admin console, by the owner): MagicDNS and HTTPS certificates
enabled for the tailnet, and the `funnel` node attribute granted in the tailnet policy. The
first `scripts/funnel.sh on` prints a login.tailscale.com link if either is missing.

`PUBLIC_API_BASE_URL` in `.env.prod` must equal `https://<host>.<tailnet>.ts.net` (no trailing
slash; `funnel.sh status` warns when it differs). Everything public derives from it:

| Use | Value |
| --- | --- |
| Strava OAuth redirect URI (compose sets `STRAVA_REDIRECT_URI`) | `$PUBLIC_API_BASE_URL/auth/strava/callback` |
| Strava "Authorization Callback Domain" | the host part, `<host>.<tailnet>.ts.net` |
| Strava webhook subscription `callback_url` (P7.7) | `$PUBLIC_API_BASE_URL/webhooks/strava` |
| Vercel `TRAINSYNC_API_URL` / `TRAINSYNC_PUBLIC_API_URL` (P7.6) | `$PUBLIC_API_BASE_URL` |

The web app calls the backend from its server-side BFF, so no CORS configuration is involved.

`make public-check` (`scripts/public_check.py`) builds its matrix from
`deploy/gateway/routes.toml`: the URL must be https with a certificate that verifies, every
allowlisted route's probe is forwarded (not 404, not 5xx), every blocked probe (`/metrics`,
`/docs`, `/`, …) is 404, and `/health/live` carries the gateway's security headers. The
scheduled workflow `.github/workflows/public-check.yml` runs it every 6 hours from GitHub's
network once the repository variable `PUBLIC_CHECK_URL` is set (it skips while it is not).
GitHub runs schedules only from the default branch, so it starts after the Phase 7 merge.

### Limits and the fallback

- Funnel is a Tailscale beta feature: behaviour and limits can change, and it can be switched off
  for the tailnet.
- Funnel traffic is relayed through Tailscale's servers with bandwidth limits that are not
  published as numbers; fine for an API, webhooks and a personal dashboard, not for bulk
  downloads. Only ports 443, 8443 and 10000 can be public.
- The hostname is tied to the tailnet name; renaming the machine or the tailnet changes the URL
  (and with it Strava's callback domain and the webhook subscription).
- Fallback: **Cloudflare Tunnel** with an own domain. `cloudflared` runs as one more compose
  service (or a LaunchAgent) with an outbound tunnel to Cloudflare, routed to the same gateway
  `127.0.0.1:8080`; set `PUBLIC_API_BASE_URL` to the new `https://api.<domain>`, update Strava's
  callback domain, re-create the webhook subscription, update Vercel, and point
  `PUBLIC_CHECK_URL` at it. Nothing in the app or the gateway changes.

## Owner checks

Manual checks only the owner can perform. Each one stays PENDING until the owner runs the
command and pastes the output here with the date. Never fill in output that was not produced by
that command on the Mac.

| # | Check | Command | Status | Date | Output |
| --- | --- | --- | --- | --- | --- |
| 1 | Docker Desktop starts at login | Docker Desktop → Settings → General → enable "Start Docker Desktop when you sign in", then `grep -o '"AutoStart": *[a-z]*' ~/Library/Group\ Containers/group.com.docker/settings-store.json` | PENDING | | (agent read-only look on 2026-10-18: `"AutoStart": false`) |
| 2 | No sleep on power | `sudo pmset -c sleep 0 disksleep 0` (if needed), then `pmset -g custom \| sed -n '/AC Power/,$p'` | PENDING | | |
| 3 | Login after reboot (FileVault / automatic login) | decide (see Reboot), then `fdesetup status` and `defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser` | PENDING | | |
| 4 | `.env.prod` filled in | `cp .env.prod.example .env.prod && chmod 600 .env.prod`, fill it in, then `ls -l .env.prod` | PENDING | | |
| 5 | LaunchAgent installed | `scripts/mac-prod.sh install-agent && launchctl print gui/$(id -u)/com.trainsync.stack \| head -5` | PENDING | | |
| 6 | Doctor clean | `scripts/mac-prod.sh doctor` | PENDING | | |
| 7 | Reboot test | the Reboot test procedure above | PENDING | | |
| 8 | Funnel prerequisites (MagicDNS, HTTPS certificates, `funnel` node attribute) | Tailscale admin console, then `tailscale funnel status` | PENDING | | (agent read-only look on 2026-10-18: Tailscale up as `trainsync`, `No serve config`) |
| 9 | Funnel on | `scripts/funnel.sh on && scripts/funnel.sh status` | PENDING | | |
| 10 | `PUBLIC_API_BASE_URL` set | put the value from `funnel.sh status` into `.env.prod`, `scripts/mac-prod.sh up` (recreates the containers with the new env; `restart` would not), then `grep PUBLIC_API_BASE_URL .env.prod` | PENDING | | |
| 11 | Public check from outside (real URL) | `make public-check URL=https://<host>.<tailnet>.ts.net` | PENDING | | |
| 12 | Scheduled public check | `gh variable set PUBLIC_CHECK_URL --body https://<host>.<tailnet>.ts.net && gh workflow run public-check.yml`, then `gh run list --workflow public-check.yml -L 1` | PENDING | | |

## Backups and restore

See P7.4.
