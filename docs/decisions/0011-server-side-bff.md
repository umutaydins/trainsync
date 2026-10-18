# 0011 — Server-side BFF instead of calling the API from the browser

- Status: accepted (writes added in phase 6, P6.5)
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
  Phase 6 extends this to writes; see "Writes (phase 6)" below.
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

## Writes (phase 6)
The training, nutrition and check-in pages write through the same route. The rules live in one
table, `RULES` in `lib/upstream.ts`, and are tested table-driven (`tests/bff-write.test.ts`):

| Path (under `/api/ts`)                                   | Methods                 |
|----------------------------------------------------------|-------------------------|
| `/v1/activities`, `/v1/activities/{id}`                  | GET                     |
| `/v1/stats/weekly`, `/v1/stats/summary`, `/v1/sync/status` | GET                   |
| `/v1/training/**`, `/v1/nutrition/**`, `/v1/checkins/**` | GET, POST, PUT, DELETE  |

`**` includes the root (`/v1/training`). Check-ins (P6.9) are in the table already so their web
part needs no BFF change.

- **Rejections, in this order** (all `{error}` JSON, `Cache-Control: no-store`, nothing forwarded):
  1. no valid session → `401` (proxy.ts, unchanged);
  2. path matches no rule → `404` (unchanged for reads); path matches with another method
     (e.g. `PATCH` outside `/v1/nutrition/foods/{id}` and `/v1/training/exercises/{id}`, `POST /v1/sync/status`) → `405` with `Allow`;
  3. mutation whose `Origin` (or, without one, `Referer`) is not the dashboard's origin → `403`;
  4. mutation without a valid `X-CSRF-Token` equal to the `ts_csrf` cookie → `403`;
  5. `POST`/`PUT` without `Content-Type: application/json` (a `DELETE` may have no body; if it has
     one, the same rule applies) → `415`;
  6. body over 64 KB → `413` (an over-limit `Content-Length` fails early, but the stream is always
     read with a byte cap, so a wrong or missing length cannot get more through);
  7. non-empty body that does not parse as JSON → `400`.
- **Path safety.** Every segment must match `[A-Za-z0-9_~-][A-Za-z0-9_.~-]{0,127}` (at most 16
  segments) before any rule is tried. Next.js hands the route decoded segments, so `..`, `.`,
  `%2e%2e`, encoded `/` or `\`, `%`, `?`, `#`, `@`, NUL and whitespace are all rejected (404) and a
  `**` rule cannot be escaped once the URL is assembled. Tested with each of them.
- **CSRF: same origin + double submit.** The session cookie stays `httpOnly`, `sameSite=lax`.
  - The allowed origin is `WEB_PUBLIC_URL`, the web app's own browser-facing URL that it already
    uses for the OAuth `return_to`. The task named `DASHBOARD_PUBLIC_URL`, but that is the
    bot/worker's setting for links *to* the dashboard and is not part of the web app's
    environment; both should hold the same URL in a deployment. `Origin: null` and an unparseable
    `Referer` count as a mismatch. Reads need no CSRF check (they change nothing and `GET` is
    already same-origin by CORS for reading the answer).
  - `ts_csrf` cookie: 32 random bytes (base64url), **not** `httpOnly` (the page copies it into
    the header), `sameSite=strict`, `Secure` under the same rule as the session cookie, 7 days.
    Login sets a fresh one; `proxy.ts` issues one to any signed-in request without a well-formed
    one (sessions from before this change, a cleared cookie); logout deletes it. The header and
    cookie are compared with `timingSafeEqual` after a format check.
  - Why both: the origin check alone stops a cross-site form or `fetch`; the token also covers a
    browser or proxy that drops `Origin`/`Referer`, and the JSON content type forces a CORS
    preflight a foreign site cannot pass.
- **Client helper.** `lib/mutate.ts` (`mutate(method, path, body)`, and `post`/`put`/`del`) reads
  the cookie, sends JSON with `X-CSRF-Token` to `/api/ts<path>`, and returns
  `{ok: true, status, data}` or `{ok: false, status, error, detail?}`; a network failure is
  `status: 0` (for the set-logging retry queue) instead of a throw. Client modules import only
  `lib/csrf-cookie.ts` (names, no secrets).
- **Answers.** Upstream status passes through (`201`, `204` without a body, `409`, `422` …). Errors
  are `{error}` like reads plus the API's `detail` for mutations, so forms can show field errors;
  upstream `401`/`403` stay opaque. The BFF builds fresh responses: no upstream header (or cookie)
  is ever copied, and the browser's cookies and CSRF header are never sent upstream.
- **Bundle check.** `scripts/check-bundle.mjs` now also fails if the `X-API-Key` header name shows
  up in a browser-served file, i.e. if any client module pulled in the upstream call path.

## Alternatives considered
- Browser calls the API directly with the key — leaks the key; ruled out.
- Browser calls the API with a per-user token (OAuth/OIDC on the API) — real auth on the API for a
  single user is far more machinery than the threat needs, and the bot would need it too.
- A generic reverse proxy (`rewrites` to the API with the key injected) — easy to forward more than
  intended (`/metrics`, `/auth/*`, non-GET); an explicit allowlisted handler is small and testable.
- NextAuth/Auth.js for the gate — a provider framework for one password is overkill; a signed
  cookie is ~40 lines and fully tested.
- Writes through Next.js server actions — they carry their own origin check, but every page would
  need its own server-side call path, and the set logger wants a plain `fetch` it can retry from a
  queue. One route with one allowlist keeps the key handling in one place.
- A CSRF token signed with the session secret (no cookie) — equally safe here; the plain
  double-submit cookie is simpler to read from the client and to rotate on login.

## Consequences
- Every browser read costs one extra hop (web → API) inside the same network; negligible here.
- New read endpoints must be added to the allowlist in `lib/upstream.ts` deliberately. Anything
  new under `/v1/training`, `/v1/nutrition` or `/v1/checkins` is reachable (GET/POST/PUT/DELETE)
  without a BFF change; other prefixes need a new row in `RULES`. `PATCH` is allowed only on `/v1/nutrition/foods/{id}` and `/v1/training/exercises/{id}` (partial updates).
- Writes only work when the dashboard is opened at exactly `WEB_PUBLIC_URL` (scheme, host and
  port): `http://127.0.0.1:3000` against `http://localhost:3000` gets 403 on every write.
- The dashboard password is the only secret between the internet and the data if `web` is exposed:
  use a long password and TLS (the cookie is `Secure` in production). The login rate limit slows
  guessing to 5 tries per address per 15 minutes, but it trusts `X-Forwarded-For`: exposed without
  a reverse proxy, a client can send its own header and rotate addresses. Put the app behind a
  reverse proxy that sets the header (or a VPN) if it is reachable from the internet.
- Rotating `DASHBOARD_SESSION_SECRET` signs everyone out, which is the intended way to revoke.
