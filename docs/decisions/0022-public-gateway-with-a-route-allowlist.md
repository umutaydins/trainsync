# 0022 — Production compose with a public-route gateway (Caddy, path allowlist)

- Status: accepted
- Date: 2026-10-18

## Context
Phase 7 exposes the backend on the internet (Tailscale Funnel, P7.3). The API process serves
more than the outside world needs: `/metrics`, `/docs`, `/openapi.json`, and every future
endpoint the moment it is merged. Funnel forwards a whole port, so whatever listens there is
public. Postgres and Redis must never be reachable, and a missing secret must stop the stack
instead of starting it half-configured.

## Decision
- `compose.prod.yml` is separate from the dev `docker-compose.yml` (no fake Strava, no dev
  defaults). Every secret is `${VAR:?set VAR in .env.prod}`, so compose refuses to start without
  it; the app also exits with `missing or invalid settings: NAME (missing)` instead of a traceback.
- Postgres and Redis are on an `internal: true` network with no published ports. The only
  published port is the gateway on `127.0.0.1:8080`; Funnel terminates TLS in front of it.
- The gateway is Caddy (pinned 2.11.7 plus `caddy-ratelimit` v0.1.0) with a **path allowlist**:
  `/webhooks/strava*`, `/auth/strava/*`, `/v1/*`, `/health/*`, and the docs only with
  `EXPOSE_DOCS=true`. Everything else is 404. Each route has a body limit; `/auth/*` has a
  per-client-IP rate limit (20/min, client IP from Funnel's `X-Forwarded-For`).
- The allowlist lives in one file, `deploy/gateway/routes.toml`. The Caddyfile is rendered from
  it (a test fails when it is stale), and `make prod-check` (also a CI job) builds its curl
  matrix from it. Later phases add routes there (e.g. the Phase 8 upload with a larger limit).

## Alternatives considered
- Expose the API directly and hide paths in FastAPI — every new router is public by default,
  and the internal `/metrics` would need its own auth. A deny-by-default edge is simpler to reason about.
- Funnel's own path routing (`tailscale serve --set-path`) — per-path config lives outside the
  repo, has no body limits or rate limits, and would not move to a VPS.
- nginx — equally capable, but Caddy's config is shorter and the same gateway gets automatic
  HTTPS on a VPS later (ADR for portability, P7.10).

## Consequences
- Adding a public endpoint is a deliberate change to `routes.toml` (reviewed, tested).
- The rate-limit module is a third-party Caddy plugin: the gateway image is a custom build, and
  its versions must be bumped together.
- The web app (Vercel) reaches only `/v1/*` through the gateway, like every other client.
