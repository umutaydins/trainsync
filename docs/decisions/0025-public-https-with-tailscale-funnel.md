# 0025 — Public HTTPS with Tailscale Funnel, checked from outside

- Status: accepted
- Date: 2026-10-18

## Context
Strava's OAuth callback and webhooks, the Vercel BFF and the Apple Health Shortcut (Phase 9) need
a stable public HTTPS URL for the backend on the MacBook. There is no domain, the Mac sits behind
a home router, and nothing should be exposed besides the gateway's allowlist (ADR 0022).

## Decision
- **Tailscale Funnel**: `https://<mac>.<tailnet>.ts.net` (port 443) forwards to the gateway on
  `127.0.0.1:8080`; port 8443 forwards to the demo gateway on `127.0.0.1:8081` (P7.9).
  `scripts/funnel.sh on|off|status` wraps `tailscale funnel --bg`, so the config lives in
  tailscaled and survives reboots. Funnel only forwards whole ports; path filtering stays in the
  gateway.
- `PUBLIC_API_BASE_URL` (`.env.prod`) is the single public base: compose derives the OAuth
  redirect URI from it, and the webhook `callback_url` and the Vercel API URL are documented as
  `<base>/webhooks/strava` and `<base>`. `funnel.sh status` prints all of them from the node's
  MagicDNS name and warns when `.env.prod` differs.
- `make public-check URL=…` checks from outside: valid TLS via an ordinary verifying HTTPS
  request, allowlisted probes forwarded, blocked probes 404, security headers; the matrix comes
  from `deploy/gateway/routes.toml` like `make prod-check`. A scheduled GitHub Actions workflow
  runs it every 6 hours against the repository variable `PUBLIC_CHECK_URL` and skips while unset.

## Alternatives considered
- Cloudflare Tunnel — needs an own domain on Cloudflare; kept as the documented fallback, since
  only `PUBLIC_API_BASE_URL` and the external registrations change.
- Port forwarding on the router plus a dynamic DNS name — exposes the home IP, needs certificate
  management on the Mac, and depends on the ISP allowing inbound 443.
- A small VPS as a reverse proxy over Tailscale — a second machine to maintain and pay for; the
  later move to a VPS (P7.10) will run the whole stack there instead.

## Consequences
- Funnel is beta and bandwidth-limited; fine for API and webhook traffic, and the public check
  notices when it stops working.
- The public hostname is tied to the machine and tailnet names; renaming either means updating
  Strava, Vercel and `PUBLIC_CHECK_URL`.
- Enabling Funnel needs owner steps in the Tailscale admin console (HTTPS certificates, the
  `funnel` node attribute); recorded under "Owner checks" in `docs/operations.md`.
