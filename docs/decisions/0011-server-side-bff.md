# 0011 — Server-side BFF instead of calling the API from the browser

- Status: accepted
- Date: 2026-10-18

## Context
The web dashboard (`web/`, Next.js) reads the trainsync read API, which authenticates every request
with a static `X-API-Key`. A key that reaches the browser (bundle, network tab, local storage) is a
key anyone with the page can copy and use against every `/v1/*` endpoint, without expiry. The
dashboard is single-user and private, so it also needs its own access gate.

## Decision
- The browser never talks to the API. Client components call a backend-for-frontend route in the
  same Next.js app, `GET /api/ts/<path>`, which forwards **GET only** to an allowlist of read paths
  (`/v1/activities`, `/v1/activities/{id}`, `/v1/stats/weekly`, `/v1/stats/summary`,
  `/v1/sync/status`), adds `X-API-Key` from the server-only `TRAINSYNC_API_KEY`, passes the query
  string through and maps upstream errors to `{error}` with the upstream status. Server components
  call the same function directly (`lib/upstream.ts` via the typed `lib/api.ts`).
- Server modules import `server-only`, so importing them from a client component fails the build.
  `make web-verify` builds with canary secrets and fails if any of them appears under
  `.next/static` or `public/` (`scripts/check-bundle.mjs`); a unit test asserts BFF responses never
  contain the key.
- Access gate: Next.js `proxy.ts` (the Next 16 name for `middleware.ts`) requires a session cookie
  on every page and BFF call. `/login` checks `DASHBOARD_PASSWORD` with a constant-time compare and
  sets an `httpOnly`, `sameSite=lax`, `secure` (in production) cookie signed with HMAC-SHA256
  (`DASHBOARD_SESSION_SECRET`), valid for 7 days. Logout deletes it.
- Login rate limit: at most 5 failed attempts per client address per 15 minutes (a fixed window
  from the first failure, `lib/login-limit.ts`). Then `/api/auth/login` answers 429 with
  `Retry-After` until the window ends, even for the right password, so a blocked address cannot
  keep guessing; a successful login clears the address's failures. The counter lives in the `web`
  process's memory: there is one `web` process, and a restart only forgets failures, which is
  acceptable for one user (no Redis dependency for the web app). The client address is the last
  `X-Forwarded-For` entry: Next.js fills the header from the socket when it is absent, and a
  reverse proxy appends the address it saw.
- Response types are generated from `docs/openapi.json` (`pnpm gen:api`, committed); a test fails
  when they are stale.

## Alternatives considered
- Browser calls the API directly with the key — leaks the key; ruled out.
- Browser calls the API with a per-user token (OAuth/OIDC on the API) — real auth on the API for a
  single user is far more machinery than the threat needs, and the bot would need it too.
- A generic reverse proxy (`rewrites` to the API with the key injected) — easy to forward more than
  intended (`/metrics`, `/auth/*`, non-GET); an explicit allowlisted handler is small and testable.
- NextAuth/Auth.js for the gate — a provider framework for one password is overkill; a signed
  cookie is ~40 lines and fully tested.

## Consequences
- Every browser read costs one extra hop (web → API) inside the same network; negligible here.
- New read endpoints must be added to the allowlist in `lib/upstream.ts` deliberately.
- The dashboard password is the only secret between the internet and the data if `web` is exposed:
  use a long password and TLS (the cookie is `Secure` in production). The login rate limit slows
  guessing to 5 tries per address per 15 minutes, but it trusts `X-Forwarded-For`: exposed without
  a reverse proxy, a client can send its own header and rotate addresses. Put the app behind a
  reverse proxy that sets the header (or a VPN) if it is reachable from the internet.
- Rotating `DASHBOARD_SESSION_SECRET` signs everyone out, which is the intended way to revoke.
