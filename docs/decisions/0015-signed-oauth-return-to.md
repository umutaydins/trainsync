# 0015 — Allowlisted `return_to` signed into the OAuth state

- Status: accepted
- Date: 2026-10-18

## Context
The web dashboard's "Connect Strava" button sends the browser to the API's `/auth/strava/login`.
After Strava redirects to the API callback, the browser should land back on the dashboard's `/sync`
page instead of a JSON body. A redirect target taken from a request parameter is the classic open
redirect: `.../login?return_to=https://evil.example` would turn our domain into a phishing hop.

## Decision
- `GET /auth/strava/login?return_to=<url>` accepts the value only if it **exactly** equals an entry
  of `OAUTH_RETURN_TO_ALLOWLIST` (comma-separated, empty by default). No prefix, host or pattern
  matching, so look-alikes (`/sync.evil`, `@evil`, `..`, other ports or case) are ignored.
- An accepted value is carried inside the signed OAuth `state` as a fourth part
  (`<nonce>.<issued_at>.<return_to>.<hmac>`); the HMAC covers it, so it cannot be swapped or
  added on the way through Strava. States without it keep the old three-part format.
- The callback re-checks the signed value against the *current* allowlist, then answers with a 303
  to `return_to?connected=1` (or `?connect_error=<reason>` for failures after a valid state).
  Without a valid `return_to` the callback behaves exactly as before (JSON or 400).

## Alternatives considered
- A cookie set by `/login` holding the target — needs another signed value and cookie handling on
  the API, which otherwise has no cookies.
- A single fixed `POST_CONNECT_URL` setting — simplest, but every connect (including the compose
  smoke test with curl) would be redirected; the parameter keeps JSON as the default.
- Prefix/origin matching — convenient, and the usual source of open-redirect bypasses.

## Consequences
- Off-allowlist values are silently ignored (logged as `oauth_return_to_ignored`), proven by
  `tests/unit/test_auth.py`.
- Adding a dashboard URL means changing `OAUTH_RETURN_TO_ALLOWLIST` on the API.
