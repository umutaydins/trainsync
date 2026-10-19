# 0036 — One bot for everyone: chat linking, acting as a user, per-user settings and schedules

- Status: accepted
- Date: 2026-10-19

## Context
The bot answered an allowlist of chats with the owner's data, and the worker sent check-ins,
reminders and coach messages to one chat at times from global settings (`CHECKIN_TIME`,
`CHECKIN_TZ`, `QUIET_HOURS`, `BOT_*`). The bot is an HTTP client of the read API with an API key
and never touches the database (ADR 0012, 0013); that should stay.

## Decision
- **Linking**: the dashboard asks `POST /v1/me/telegram/code` for a one-time code (8 characters
  from an unambiguous alphabet, stored in Redis for `TELEGRAM_LINK_CODE_TTL_MINUTES`=10, deleted
  on use). The user sends `/link CODE` to the bot; the bot calls
  `POST /v1/telegram/chats/{chat_id}/link` with the code; the chat is bound to the account
  (`telegram_chats`: chat id → user, one chat per user). `/unlink` removes the binding.
- **Unknown chats** get one short reply, "link your account at `<DASHBOARD_PUBLIC_URL>`", and
  nothing else: no command runs, no assistant call.
- **Acting as the linked user**: the bot keeps its API key and adds `X-Acting-User: <user id>`
  to every call for a linked chat. The API accepts that header only from a key listed in
  `SERVICE_API_KEYS` (the bot's), so other key holders act as the owner only. The chat → user
  lookup (`GET /v1/telegram/chats/{chat_id}`) returns the user id and their settings and is
  cached in the bot for a minute; `/link`, `/unlink`, `/lang` and `/swear` drop the cache entry.
- **Per-user settings** (`user_settings`, one row per user): tone, intensity, profanity,
  language, check-in on/off and time, reminder minutes, quiet hours, workout reminder time, sugar
  limit, country. The environment values (`BOT_TONE`, `CHECKIN_TIME`, …) become the defaults of a
  new user's row. `/lang` and `/swear` write the linked user's settings. The emergency number in
  the distress reply comes from the country (`EMERGENCY_NUMBERS`, e.g. US 911, GB 999, AU 000),
  falling back to `EMERGENCY_NUMBER`.
- **Schedules per user**: the worker crons iterate users with a linked chat and compute "now",
  "today" and quiet hours in each user's time zone; notifications are claimed per
  `(user_id, kind, object_id)`. `TELEGRAM_ALLOWED_CHAT_IDS` is only the owner's bootstrap: the
  migration links those chats to the owner.
- **Assistant cost**: the owner pays for the API key, so each user gets
  `ASSISTANT_DAILY_LIMIT` (50) questions per local day (Redis counter); the owner is exempt.
  The hourly per-chat limit stays.

## Alternatives considered
- One bot token per user — every user would have to create a bot.
- Give the bot database access to resolve chats — breaks ADR 0012/0013 and spreads DB credentials.
- A per-user API token for the bot — the bot would have to store secrets per chat.

## Consequences
- A leaked bot key can act as any user: it is one of the most sensitive secrets, separate from
  the owner's tooling keys, and the gateway never forwards `X-Acting-User` from outside.
- Users without a linked chat get no timed messages; that is the opt-in.
