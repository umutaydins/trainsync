# Phase 8 — Multi-user

Goal: trainsync becomes a multi-user app. Anyone with an invite can create an account; every user
has their own data, Strava connection, Telegram link and coach settings, and no request can read
or write another user's rows. The owner keeps every existing row (migrated to the owner account)
and stays the only one who can invite, reset passwords and see the user list.

The owner authorised this phase on 2026-10-19 while Phase 7 still has pending owner checks
(`docs/operations.md` → Owner checks); nothing here is deployed until those pass.

## Tasks
1. Accounts and sessions: users, argon2id passwords, opaque session tokens (hashed, sliding,
   revocable), register / login / logout / me / change password, rate limits and lockout,
   invites (`REGISTRATION_MODE`), owner-generated reset links, owner CLIs (P8.1, ADR 0034).
2. Tenant isolation: `user_id` on every user-owned table, every query scoped by the current user,
   the single-user → owner migration, the IDOR suite (P8.2, ADR 0035).
3. Strava per user: OAuth bound to the logged-in user, one athlete per user, webhooks routed to
   the athlete's user, fair backfill scheduling (P8.3, ADR 0037).
4. Telegram per user: one bot, `/link CODE`, `/unlink`, unknown chats pointed to the dashboard,
   the bot acting as the linked user (P8.4, ADR 0036).
5. Per-user settings and schedules: tone, intensity, profanity, language, check-in time, time
   zone, quiet hours, reminder time, sugar limit, country (emergency number); crons per user;
   assistant daily limit (P8.5, ADR 0036).
6. Account deletion (soft delete + purge + Strava deauthorize) and JSON data export (P8.6,
   ADR 0037).
7. Web BFF: the session cookie carries the API token; register / login / logout / me / invite /
   Telegram code / settings / export / delete handlers; the shared API key leaves user requests
   (P8.7).
8. Gateway and operations: Caddy allowlist and public-check, env examples, operations.md
   (invite, reset, delete), demo user, backup counts (P8.8).
9. Phase gate (P8.9).

## Acceptance criteria
- With `REGISTRATION_MODE=invite` an account needs an unused, unexpired invite; `open` needs none;
  `closed` refuses every registration (tests).
- Passwords are stored as argon2id hashes; session tokens only as SHA-256 hashes; a revoked or
  expired token is refused; the expiry slides on use up to an absolute maximum (tests).
- The sixth failed login for one email inside the window is locked out even with the right
  password, and per-address limits hold for login and register (tests with a fake clock).
- For every user-owned endpoint, user B gets 404 for user A's ids and list endpoints never return
  A's rows; the suite is generated from the OpenAPI document so new endpoints are covered (test).
- The migration on seeded single-user data assigns every row to the owner from `OWNER_EMAIL`,
  links the bootstrap Telegram chats, is idempotent and reversible (integration test), and the
  backup image restores a pre-phase dump that then migrates cleanly (restore-check-ci).
- A Strava athlete belongs to one user; the OAuth state names the user; a webhook for an athlete
  only touches that athlete's user; one big backfill does not delay another athlete's sync (tests).
- An unlinked chat gets only the "link your account" reply; `/link CODE` binds it once; `/unlink`
  unbinds; every bot request acts as the linked user (tests).
- Crons run per user in the user's time zone and quiet hours (tests with a fake clock).
- The assistant stops answering a user after `ASSISTANT_DAILY_LIMIT` questions in their local day;
  the owner is exempt (test).
- Export returns every row the user owns; deletion revokes sessions at once and the purge job
  removes all of the user's rows and deauthorizes Strava (tests).
- `make verify`, `make web-verify`, `make prod-check`, `make demo-check`, `make compose-smoke`,
  `make restore-check-ci` and the fault suite are green; coverage does not drop.

## Out of scope
- Email delivery (verification, reset by email): resets are owner-generated links for now.
- OAuth / social login, 2FA, organisations or shared data between users.
- New dashboard pages (Phase 8 web UI, P8.12+): this phase keeps the existing pages compiling and
  adds the BFF and API they need.
