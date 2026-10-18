# Deploying the dashboard on Vercel (P7.6)

The web app (`web/`) runs on Vercel; the backend stays on the Mac behind Tailscale Funnel
(P7.3). The browser only talks to Vercel: the BFF there calls the backend with the API key,
server-side (ADR 0011), so the key never reaches the browser.

```
browser ──> https://<project>.vercel.app ──(server-side, X-API-Key)──> https://<mac>.<tailnet>.ts.net/v1/*
preview  ──> https://<project>-<hash>-<team>.vercel.app ──────────────> https://<mac>.<tailnet>.ts.net:8443/v1/*  (demo, P7.9)
```

## 1. Create the project
1. vercel.com → Add New → Project → import the GitHub repository.
2. **Root Directory**: `web`. Framework preset: Next.js (also pinned in `web/vercel.json`, with
   `pnpm install --frozen-lockfile` and `pnpm build`). Node version comes from `engines.node` in
   `web/package.json` (22). `output: "standalone"` in next.config.ts is for the Docker image and
   harmless on Vercel.
3. Don't deploy yet: set the environment variables first.

## 2. Environment variables (Project → Settings → Environment Variables)

| Variable | Production | Preview |
|---|---|---|
| `TRAINSYNC_API_URL` | `https://<mac>.<tailnet>.ts.net` | `https://<mac>.<tailnet>.ts.net:8443` (demo backend) |
| `TRAINSYNC_API_KEY` | one of the real `API_KEYS` (`.env.prod`) | the demo key (P7.9) |
| `TRAINSYNC_PUBLIC_API_URL` | same as `TRAINSYNC_API_URL` | same as `TRAINSYNC_API_URL` |
| `WEB_PUBLIC_URL` | `https://<project>.vercel.app` | `https://<project>.vercel.app` (previews also accept their own URL, below) |
| `DASHBOARD_PASSWORD` | your password | the public demo password (README) |
| `DASHBOARD_SESSION_SECRET` | 32+ random characters | a different 32+ random string |
| `NEXT_PUBLIC_TZ` | `Europe/Istanbul` | `Europe/Istanbul` |
| `UPSTREAM_TIMEOUT_MS` | optional, default 8000 | optional |

Mark the key, password and secret as **Sensitive**. Never give Preview the production key: a
preview build of any branch could then read your data.

**CSRF / origin**: the BFF accepts writes from `WEB_PUBLIC_URL` and from the exact URLs Vercel
gives the running deployment (`VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`,
set by Vercel automatically). No wildcard: another project, another preview or a lookalike domain
is refused (`web/tests/origins.test.ts`).

**Backend side** (`.env.prod` on the Mac, then `scripts/mac-prod.sh up`):
```
OAUTH_RETURN_TO_ALLOWLIST=https://<project>.vercel.app/sync
DASHBOARD_PUBLIC_URL=https://<project>.vercel.app
```

## 3. Protect previews
Settings → Deployment Protection → **Vercel Authentication** for Preview deployments (Standard
Protection), so only you can open a preview. Production stays public (it has its own login).

## 4. Deploy and check
Deploy `main`. Then (owner checks in operations.md):
- Production: log in, the dashboard shows your real data, "Connect Strava" goes to the Mac's
  callback and back to `/sync`.
- A preview (any PR): log in with the demo password, it shows demo data.
- Mutations work (log a set in /training) — that is the CSRF origin check passing on Vercel.
- Mac asleep or offline: the pages show "Backend unreachable", not a crash; the timeout (8 s)
  stays under Vercel's function limit.

## Notes
- The Vercel Hobby plan is for personal, non-commercial use, which this is.
- Server-side calls from Vercel to the Mac go over the public internet to the Funnel URL; only
  the gateway's allowlisted routes answer there (ADR 0022).
