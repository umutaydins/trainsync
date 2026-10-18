# 0031 — Runtime bot language per chat

- Status: accepted
- Date: 2026-10-19

## Context
`BOT_LANG` (ADR 0016) fixes the language for the whole deployment; changing it means editing
`.env.prod` and recreating the bot and the worker. The owner wants to switch between Turkish and
English from the chat. The language is read in many places: the bot's replies, the check-in
flow, the coach lines (ADR 0030), the assistant's prompt, and the worker's timed messages, which
run in another process. The savage pack existed in Turkish only.

## Decision
- **Stored per chat, through the API.** A `chat_settings` row (`chat_id`, `lang`) behind
  `GET/PUT /v1/chats/{chat_id}/settings`. The bot never touches the database (ADR 0013), so it
  writes through the API like every other bot write. No row means `BOT_LANG`, which stays the
  default for new chats and for a database without the table yet.
- **A context variable, not a `Messages` per language passed around.** `using_lang(lang)` sets
  the language for the current task; a `Messages` built by `messages_for` (and the coach voice)
  renders in that language, else its default pack. The dispatcher sets it once per update, the
  worker once per job (`in_chat_lang`, reading the row at send time), so every call site that
  already takes a `Messages` follows the chat without new parameters. The tone stays global.
- **The bot caches** the stored value per process; `/lang` updates the cache and the row. An API
  error on the read falls back to `BOT_LANG` for that update and is not cached, so the next update
  asks again.
- **Help stays English.** Command names were always English; their descriptions now are too in
  both languages (`Messages.help()` renders the tone's English help), so the command list reads the
  same whatever the chat language. This changes the Turkish help, which was Turkish before.
- **Savage in both languages.** `coach/savage_en.py` mirrors `savage_tr.py` (same categories,
  ≥ 60 original lines, unlimited profanity, the same guardrail tests). `punchline_en` moves to
  `coach/punchlines.py` and is shared. `savage_configured` no longer requires `BOT_LANG=tr`. A new
  category, `language_set`, is the savage confirmation after `/lang`.
- **Local lines per language.** `config/messages.local.yaml` has `tr:` and `en:` sections and a
  top-level `punchline_en` that goes into both; top-level categories (the P6.11 format) still load
  as Turkish, so an existing file keeps working.
- **Stack alerts** (ADR 0027) become a detail key plus fields, rendered in the chat's language;
  the English text is unchanged. The host-side uptime check stays English (it runs outside the
  stack and must work when the API and database are down).

## Alternatives considered
- Pass the language (or a `Messages`) explicitly through every call — explicit, but touches every
  formatter and feature signature for one value that is constant within an update or a job.
- Store the choice in Redis — already shared by bot and worker, but it is configuration, not a
  cache: it should survive a Redis flush and be part of the backups.
- One language per deployment, switched by editing `.env.prod` — what the owner wants to avoid.

## Consequences
- One API read per chat per bot process (cached), one database read per worker message.
- New wording needs both languages: the pack tests fail on a missing key or category, so a
  half-translated change cannot pass CI.
- Code that renders a message outside an update or a job (none today) gets `BOT_LANG`.
