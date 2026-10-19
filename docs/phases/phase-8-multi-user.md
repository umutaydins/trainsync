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
10. Progress statistics API: periods in the user's time zone with the previous period's change,
    endurance per sport group, strength (tonnage, e1RM, PRs, adherence), consistency, nutrition,
    body trend; `/v1/stats/summary`, `/series`, `/heatmap`, `/prs`; trigger-versioned Redis cache
    (P8.10, ADR 0038).
11. Stats in the bot and digests: `/stats [week|month|3m|6m|year|all]` with praise / roast, the
    Monday and 1st-of-month digests, `STATS_DIGEST_ENABLED` and a per-user switch (P8.11,
    ADR 0038).
12. Web UI foundation: design tokens in `styles/tokens.css` (dark-first + light, theme cookie),
    Geist, shadcn-style primitives on Radix / vaul, next-intl with `messages/{en,tr}/<namespace>`,
    bottom tab bar and sidebar, a service worker for the shell and an offline page, ESLint
    boundaries for `i18n/` and `styles/` (P8.12, ADR 0039).
13. Web sign-in, registration (invite / open / closed, `/invite/<code>`), forgot password and reset
    links, skippable onboarding (zone, language, coach with a preview line, Connect with Strava,
    Telegram code, nutrition profile), `/privacy` and `/terms` (P8.13, ADR 0039).
14. Web settings ("Me": profile, password, sessions, coach, digests, Telegram, Strava, export,
    deletion) and the owner's Admin (invites, users, reset links; not-found for others) (P8.14,
    ADR 0039).
15. Web Progress (period switcher, stat cards with changes, charts, year heatmap, PRs) and Today
    (week, planned workout, food, latest activity, empty states) (P8.15, ADR 0038, ADR 0039).
16. Web workout (big steppers, one-tap set done, full-screen rest timer, plate sheet), food,
    activities and sync on the new design, multi-user empty states (P8.16, ADR 0039).
17. Web UI gate: Playwright e2e, axe on every page, Lighthouse, screenshots (P8.17, ADR 0039).

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
- Stats period boundaries are local midnights, also across a DST change (two zones); the
  previous period has the same length (a calendar unit: the unit before); an empty period gives
  zeros and null changes (tests).
- e1RM ignores sets above 10 reps and warm-ups; a PR is a strictly higher e1RM than every earlier
  set of the lift; streaks and the heatmap match hand-computed fixtures (tests).
- A write to any of the user's tables changes the stats cache key; another user's write does not;
  with three years of seeded data the summary answers in under 300 ms locally (tests).
- `/stats month` answers with the month's numbers and changes in tr and en, in each tone (test).
- Monday 09:00 local sends last week's digest once per user, in two time zones; quiet hours hold
  it; the 1st sends the monthly one (tests with a fake clock).
- Web UI (P8.12–P8.17): every primitive has a unit test (role, keyboard, axe-clean render); no raw
  colour value outside `tokens.css`; `en` and `tr` messages have the same keys; at 360–430 px no
  page scrolls sideways and touch targets are at least 44 px (tests).
- invite → register → onboarding → Today → a workout → sign out → sign in works end to end; the
  Strava button and attribution use Strava's own assets (e2e).
- Changing the language switches the UI language on the next render; a user never sees Admin and
  gets the not-found page on `/admin`; another user's ids give the not-found page (e2e).
- Switching the Progress period updates every block and the URL; every block has empty, loading
  and error states (e2e, tests).
- A workout is logged end to end on a phone viewport; the existing training and nutrition tests
  stay green (e2e).
- axe finds nothing on any page in dark and light; Lighthouse (mobile) performance and
  accessibility are at least 90 on Today, Workout, Food and Progress (measured 91–98 and 100);
  `SCREENSHOTS_DIR` captures every page at 375 and 1280 px in both themes (`make web-e2e`).
- `make verify`, `make web-verify`, `make web-e2e`, `make prod-check`, `make demo-check`, `make compose-smoke`,
  `make restore-check-ci` and the fault suite are green; coverage does not drop.

## Out of scope
- Email delivery (verification, reset by email): resets are owner-generated links for now.
- OAuth / social login, 2FA, organisations or shared data between users.
- A full offline mode with cached API data (ADR 0039: the service worker caches the shell only).
