# 0029 — Backend on a personal Mac behind Tailscale Funnel; how to move it to a VPS

- Status: accepted
- Date: 2026-10-18

## Context
Phase 7 runs trainsync for real. The owner has an always-on MacBook (M1, 16 GB) and no budget
or domain for a server. The backend needs a stable public HTTPS URL for Strava (OAuth callback,
webhooks), for the Vercel-hosted web app and for the Apple Health Shortcut (Phase 9). It must stay
movable to Oracle Cloud Always Free or a small VPS later without code changes.

## Decision
- The backend runs on the Mac: `compose.prod.yml` under Docker Desktop, started at login by a
  LaunchAgent (ADR 0023), controlled by `scripts/mac-prod.sh`, deployed with `make deploy`
  (ADR 0026), backed up nightly to iCloud Drive with a tested restore (ADR 0024).
- Public HTTPS comes from Tailscale Funnel (ADR 0025): `https://<mac>.<tailnet>.ts.net` → the
  gateway on `127.0.0.1:8080` (real) and `:8443` → `127.0.0.1:8081` (demo). No domain, no open
  router port, TLS by Tailscale.
- The gateway (ADR 0022) is the only public surface, so whatever terminates TLS in front of it can
  change without touching the app.
- The web app runs on Vercel (P7.6); uptime is checked from GitHub Actions, outside the Mac (P7.8).

## What moving to a VPS / Oracle Always Free changes
| Today (Mac) | On a Linux VM | Code change |
|---|---|---|
| Tailscale Funnel terminates TLS | Caddy in the gateway terminates TLS itself: give it a hostname (a domain, or `<ip>.sslip.io`) and let it get a Let's Encrypt certificate; publish 80/443 instead of `127.0.0.1:8080` | Caddyfile site address (rendered from `routes.toml` by `scripts/render_gateway.py`); routes unchanged |
| Docker Desktop on Apple silicon (arm64 images) | Oracle Ampere A1 is arm64 too, the same images run; an x86 VPS rebuilds them (`docker compose build`, every base image is multi-arch) | none |
| LaunchAgent + `mac-prod.sh` | a systemd unit running `docker compose --env-file .env.prod -f compose.prod.yml up -d` after `docker.service`; `restart: unless-stopped` already covers crashes | a unit file; `mac-prod.sh doctor` checks are macOS-specific and stay behind |
| Backups to iCloud Drive | `BACKUP_HOST_DIR` on a block volume plus an off-site copy (object storage, `rclone`), same `age` encryption and restore check | none (path only) |
| `PUBLIC_API_BASE_URL=https://<mac>.<tailnet>.ts.net` | the new hostname; update the Strava app's callback domain, re-create the webhook subscription (`scripts/strava-subscription.py delete` / `create`), Vercel `TRAINSYNC_API_URL`, `OAUTH_RETURN_TO_ALLOWLIST` | configuration only |

Move procedure: deploy the same SHA on the VM, stop the Mac stack, `make backup-now`, restore that
backup on the VM (the restore check proves the counts), switch the URLs above, run
`make public-check URL=…` against the new host.

## Alternatives considered
- Cloud VM from day one — monthly cost (or Always Free capacity hunting) for a single user, and
  one more machine to patch; the Mac is already always on.
- Cloudflare Tunnel — needs a domain on Cloudflare; Funnel needs nothing. It stays the documented
  fallback if Funnel's limits bite (operations.md → Funnel).
- Port forwarding on the home router — exposes the home IP, needs dynamic DNS and certificate
  handling on the Mac.

## Consequences
- Availability is the Mac's: sleep, macOS updates, power or network loss take the backend down.
  Mitigations: no sleep on power (doctor checks it), start at login, external uptime alerts,
  Vercel shows "Backend unreachable" instead of failing.
- Funnel is a Tailscale beta feature with bandwidth limits; fine for one user and a demo.
- Personal data lives on a personal laptop: FileVault on, `.env.prod` and the backup identity
  outside iCloud and git, backups encrypted with `age`.
