# 0012 — Telegram first, behind a Notifier interface

- Status: accepted
- Date: 2026-10-18

## Context
Phase 5 adds a chat channel: ask "how was my week?" from anywhere, and get a short message when
a new activity arrives. The owner would eventually like WhatsApp too. This is a single-user
service on a laptop-sized deployment, without a public HTTPS endpoint of its own for the bot.

## Decision
Telegram is the first and only channel for now.
- The bot uses **long polling** (`getUpdates`), so it needs no public URL, no TLS certificate and
  no inbound port.
- Who may talk to it is an explicit allowlist of chat ids (`TELEGRAM_ALLOWED_CHAT_IDS`). Other
  chats get no reply at all, only a log line with the chat id.
- Outgoing notifications go through a small `Notifier` protocol (`async send(chat_ref, text)`)
  with `TelegramNotifier` and a `NullNotifier` (the default when no token is configured). The
  notification job only knows the protocol, so a `WhatsAppNotifier` is a drop-in later.
- The bot is a client of the read API (HTTP + API key), never of the database.

## Alternatives considered
- **WhatsApp now** (Cloud API): needs a Meta Business account and business verification,
  pre-approved message templates for anything sent outside a 24-hour customer-service window
  (every notification would be one), per-conversation pricing, and a public HTTPS webhook for
  incoming messages. A lot of process and cost for one user.
- **E-mail / push**: no conversational commands.
- **Telegram webhooks instead of polling**: needs a public HTTPS endpoint; polling costs one
  idle HTTP request every 25 s.

## Consequences
- One more long-running process (`bot`) with its own metrics port.
- The Telegram bot token is a secret like the others (`SecretStr`, never logged; it is part of
  every Bot API URL, so URLs and httpx exceptions are never logged either).
- The `Notifier` protocol is deliberately tiny (text only). Rich formatting or buttons would
  widen it; WhatsApp templates may need a `kind` + parameters form later.
