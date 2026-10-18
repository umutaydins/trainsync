# 0013 — Plain httpx for the Telegram bot, not aiogram

- Status: accepted
- Date: 2026-10-18

## Context
The bot needs two Bot API methods: `getUpdates` (long polling) and `sendMessage`, with honest
handling of 429 `retry_after` and 5xx. The same `sendMessage` is used by the worker's
`TelegramNotifier`. Tests must never hit Telegram; the repo mocks HTTP with respx.

## Decision
A ~150-line client on the process's one shared `httpx.AsyncClient`
(`trainsync/bot/telegram.py`), plus a small polling loop and a command dispatcher of our own.
- 429: wait exactly `parameters.retry_after` (through the injected `sleep`), then retry.
- 5xx / connection refused: exponential backoff 1, 2, 4 … s (capped at 30 s), bounded attempts.
- A read timeout after the request was sent is "delivery unknown" and is *not* retried by the
  client: retrying could send the same message twice (it matters for notifications, ADR 0012).
- Messages are plain text (no `parse_mode`), so activity names never need escaping.

## Alternatives considered
- **aiogram 3**: a full framework (routers, filters, FSM, middlewares) built on aiohttp. That is a
  second HTTP stack next to httpx, which respx cannot mock, so tests would need aiogram's own
  mocking or a fake server, unlike every other outbound client here. It also has its own retry,
  session and shutdown behaviour we would have to learn and test around, and pulls in
  aiohttp, aiofiles, magic-filter and friends for five commands.
- **python-telegram-bot**: same trade-off (it is on httpx, but brings its own Application
  lifecycle and job queue).

## Consequences
- Fewer dependencies, one HTTP stack, the same respx-based tests as the Strava client.
- We own the small amount of protocol code: update parsing (only `message.chat.id` and
  `message.text`), offset handling, flood control. New Bot API features (inline keyboards,
  webhooks) would be ours to add; if the bot grows a lot, revisit aiogram.
