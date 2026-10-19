# Deploying the dashboard on Vercel (P7.6)

The web app (`web/`) runs on Vercel; the backend stays on the Mac behind Tailscale Funnel
(P7.3). The browser only talks to Vercel: the BFF there calls the backend server-side
(ADR 0011) with the signed-in user's API session token, which travels sealed (AES-256-GCM) in the
httpOnly session cookie (ADR 0034). The web holds no API key.

```
browser ──> https://<project>.vercel.app ──(server-side, Bearer)─────> https://<mac>.<tailnet>.ts.net/v1/*
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
| `WEB_PUBLIC_URL` | `https://<project>.vercel.app` | `https://<project>.vercel.app` (previews also accept their own URL, below) |
| `DASHBOARD_SESSION_SECRET` | 32+ random characters | a different 32+ random string |
| `OWNER_CONTACT_EMAIL` | your contact address (shown on `/privacy` and `/terms`) | same; unset = the placeholder `owner@example.com` |
| `DASHBOARD_COOKIE_SECURE` | leave unset (`true` in a production build) | leave unset |
| `UPSTREAM_TIMEOUT_MS` | optional, default 8000 (read by `lib/upstream.ts`) | optional |

These are all the variables the web reads (`web/src/lib/env.ts`, `lib/session.ts`,
`lib/upstream.ts`), all server-side. There is no `NEXT_PUBLIC_*` setting: the time zone and
language come from each user's settings (ADR 0039), so a `NEXT_PUBLIC_TZ` left over from Phase 7
can be deleted. The service worker's shell cache is versioned by the commit
(`VERCEL_GIT_COMMIT_SHA`, set by Vercel; `web/next.config.ts`), so nothing to set for it.

Mark the session secret as **Sensitive**. Never point Preview at the production backend: a
preview build of any branch would then sign real users in. People sign in with their own email and
password (production) or with the published demo account `demo@trainsync.invalid` /
`trainsync-demo` (Preview, public on purpose: README "Live demo"); `DEMO_API_KEY` is for your own
tooling and does not go to Vercel.

**CSRF / origin**: the BFF accepts writes from `WEB_PUBLIC_URL` and from the exact URLs Vercel
gives the running deployment (`VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`,
set by Vercel automatically). No wildcard: another project, another preview or a lookalike domain
is refused (`web/tests/origins.test.ts`).

**Backend side** (`.env.prod` on the Mac, then `scripts/mac-prod.sh up`):
```
OAUTH_RETURN_TO_ALLOWLIST=https://<project>.vercel.app/sync,https://<project>.vercel.app/onboarding,https://<project>.vercel.app/me/connections
DASHBOARD_PUBLIC_URL=https://<project>.vercel.app
```
"Connect with Strava" starts on three pages (Sync, the onboarding step and Me → Connections) and
returns to the one it started on, as `<WEB_PUBLIC_URL><path>`. The allowlist is an exact match, so
all three must be in it; a missing one ends the OAuth flow on the API's JSON answer instead of the
web app.

## 3. Protect previews
Settings → Deployment Protection → **Vercel Authentication** for Preview deployments (Standard
Protection), so only you can open a preview. Production stays public (it has its own login).

**The public demo (P7.9)** is a preview, so with this protection on, visitors from the README
hit a Vercel login. Previews only ever get the demo backend (`:8443`, read-only, synthetic data,
ADR 0028) and the demo account, which is public anyway, so it is safe to turn Vercel
Authentication **off for previews** (Deployment Protection → Disabled). Keep Production on its
own login as before. The README link should be a stable branch URL
(`https://<project>-git-<branch>-<team>.vercel.app`, e.g. a `demo` branch that tracks `main`)
rather than a per-commit preview URL. This is the owner's call (owner check 29 in
[operations.md](operations.md#owner-checks)).

## 4. Deploy and check
Deploy `main`. Then (owner checks in operations.md):
- Production: sign in with your account (`docs/operations.md` → Accounts), the dashboard shows
  your data, "Connect with Strava" goes to Strava, the Mac's callback and back to the page it
  started on (`/sync`, `/onboarding` or `/me/connections`).
- A preview (any PR): sign in with `demo@trainsync.invalid` / `trainsync-demo`, it shows demo
  data.
- Mutations work (log a set in /training) — that is the CSRF origin check passing on Vercel.
- Mac asleep or offline: the pages show "Backend unreachable", not a crash; the timeout (8 s)
  stays under Vercel's function limit.

## Notes
- The Vercel Hobby plan is for personal, non-commercial use, which this is.
- Server-side calls from Vercel to the Mac go over the public internet to the Funnel URL; only
  the gateway's allowlisted routes answer there (ADR 0022).
