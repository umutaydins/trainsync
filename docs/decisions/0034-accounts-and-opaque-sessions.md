# 0034 — Accounts, opaque sessions, invites and owner resets

- Status: accepted
- Date: 2026-10-19

## Context
Phase 8 opens trainsync to more people than the owner. Until now every request carried one
shared API key (and the web had one dashboard password). We need per-person accounts that are
safe on a public URL, cheap to run on a single Mac, without an email provider.

## Decision
- **Users** (`users`): email (stored lower-cased and trimmed, unique), argon2id password hash
  (argon2-cffi, RFC 9106 low-memory parameters), display name, role `owner | user`, time zone,
  `created_at`, `deleted_at`. Passwords: 10–128 characters, no composition rules (NIST
  SP 800-63B). Exactly one owner (partial unique index).
- **Sessions** (`sessions`): a random 32-byte token (base64url) is handed out once; only its
  SHA-256 is stored. A request presents it as `Authorization: Bearer <token>`. Expiry
  `SESSION_TTL_DAYS` (30) slides forward on use (written at most every
  `SESSION_TOUCH_INTERVAL_S`), capped at `SESSION_MAX_AGE_DAYS` (90) after creation. Logout,
  "revoke this session", password change (all other sessions) and deletion revoke rows.
  Opaque tokens instead of JWTs: revocation is a row update and nothing secret lives in the
  client.
- **Registration**: `REGISTRATION_MODE=invite|open|closed` (default `invite`). Invites are
  single-use random codes (stored hashed) with an expiry (`INVITE_TTL_DAYS`, 7), created by the
  owner through `scripts/invite.py create|list|revoke` or the owner-only API.
- **Abuse limits** (Redis, fixed windows, injected clock): login failures per email
  (`LOGIN_MAX_FAILURES`=5 per `LOGIN_LOCKOUT_MINUTES`=15 → locked for that long, even with the
  right password) and per client address (`LOGIN_MAX_FAILURES_PER_IP`=20); registrations per
  address (`REGISTER_MAX_PER_HOUR`=5). Unknown emails are hashed against a dummy hash so timing
  does not reveal which emails exist; login errors are one generic message.
- **Password reset without email**: the owner runs `scripts/owner.py reset-link EMAIL` (or the
  owner API) and gets a one-time link `<DASHBOARD_PUBLIC_URL>/reset-password?token=…`
  (token hashed, `RESET_TTL_MINUTES`=60). Using it sets the password and revokes all sessions.
  Email delivery is a later task.
- **Owner bootstrap**: the migration creates the owner from `OWNER_EMAIL` with an unusable
  password; `scripts/owner.py set-password` sets it.
- The **API key** (`API_KEYS`) stays for machine and owner tooling (the bot, scripts, monitors):
  a request with a valid key acts as the owner, or as the user named in `X-Acting-User` when the
  caller is a trusted service (ADR 0036).

## Alternatives considered
- JWT access + refresh tokens — stateless checks we do not need on one database; revocation
  needs a deny list anyway.
- bcrypt — fine, but argon2id is the current OWASP first choice and memory-hard.
- Email verification and reset mails — needs a provider (cost, deliverability, a secret);
  owner-generated links are enough for an invite-only app.
- Rate limits in Postgres — Redis TTL counters are simpler and already in the stack.

## Consequences
- The web BFF stores the session token in an httpOnly cookie and sends it as a Bearer token; the
  shared API key no longer reaches user requests.
- Lost-password support is manual (owner CLI) until email exists.
- argon2id costs ~50 ms and 64 MiB per hash: fine at login rates, and the register/login limits
  keep it from being a DoS lever.
