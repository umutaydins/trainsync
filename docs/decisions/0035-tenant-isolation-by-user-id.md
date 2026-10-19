# 0035 — Tenant isolation by `user_id`, and the single-user migration

- Status: accepted
- Date: 2026-10-19

## Context
Every table was written for one person: one nutrition profile row (`id = 1`), body metrics keyed
by date, one active program, check-ins unique per day. With several users, any query that forgets
a filter leaks someone's training or body data, and an idempotent `PUT` by client id could
overwrite another user's row.

## Decision
- **Every user-owned table gets `user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE`
  and an index led by it**: athletes, oauth_tokens, activities, sync_runs, programs,
  program_days, program_exercises, workouts, workout_sets, body_metrics, daily_checkins,
  food_logs, nutrition_profile, notifications, user_settings, telegram_chats. `webhook_events`
  stays without a user (it is routed through the athlete). Shared tables stay shared: built-in
  exercises and the food catalogue / Open Food Facts cache. Custom exercises and manual foods get
  a nullable `user_id` (null = shared) and are only visible to their owner; favourites move to
  `food_favorites (user_id, food_id)`.
- **Uniqueness is per user**: `(user_id, client_id)` for workouts, sets and food logs (an
  idempotent `PUT` can never hit another user's row), `(user_id, date)` for body metrics and
  check-ins, one active program per user, one nutrition profile per user, notifications unique
  per `(user_id, kind, object_id)`.
- **Scoping in the repositories**: every repository that reads or writes user-owned rows takes
  the user id in its constructor (`TrainingRepository(session, user_id)`) and adds it to every
  statement; routers get the user from the `CurrentUser` dependency. Not-yours and missing look
  the same: 404.
- **IDOR suite**: an integration test builds two users, creates resources as A, then walks the
  OpenAPI document and calls every user-owned path with A's ids as B, expecting 404 (and lists
  without A's rows). A new endpoint is covered without editing the test.
- **Migration from single-user** (0015–0017): create `users`; if any user-owned row exists,
  require `OWNER_EMAIL` and create the owner (unusable password) — otherwise no owner is created;
  add the columns nullable, fill them with the owner's id, then set `NOT NULL` and swap the
  unique constraints. Bootstrap chats from `TELEGRAM_ALLOWED_CHAT_IDS` are linked to the owner,
  and existing `chat_settings` move into `user_settings`. Every step is guarded so a re-run is a
  no-op; downgrade restores the single-user schema with the owner's data.

## Alternatives considered
- Postgres row-level security with a session variable — a second enforcement layer worth adding
  later; on its own it makes every query depend on connection state and is harder to test.
- A schema or database per user — heavy for a handful of users on one Mac.
- A request-scoped context variable read by the repositories — invisible in signatures; one
  forgotten `with` would silently read as "no user".

## Consequences
- Every repository call site names the user, which reviews can see.
- Composite unique constraints change the `ON CONFLICT` targets of the idempotent writes.
- The demo seed creates a demo user and seeds everything under it.
