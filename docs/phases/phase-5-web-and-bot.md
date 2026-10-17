# Phase 5 — Web dashboard and Telegram bot

Goal: make the data usable day to day — a small private web dashboard and a Telegram bot that
answers questions and announces new activities — without weakening the backend's guarantees.

## Tasks
1. Read API additions the clients need (activity detail, range summary).
2. `web/`: Next.js (App Router, TypeScript, Tailwind) with a server-side BFF that holds the API key;
   the browser never sees it. Single-user access gate.
3. Dashboard (weekly volume chart, totals by sport), activity list with filters and keyset
   paging, activity detail.
4. Sync status page and "Connect Strava" button; Playwright e2e against the compose stack.
5. Telegram bot process (long polling): `/week`, `/last`, `/stats`, `/status`; chat allowlist.
6. New-activity notifications through a `Notifier` interface (Telegram now, WhatsApp later),
   idempotent per activity.
7. Optional: natural-language questions in the bot using Claude tool use over the read API.

## Acceptance criteria
- `make verify` and `make web-verify` green; CI runs both.
- The API key never reaches the browser (test asserts on built client bundles and responses).
- Dashboard numbers match `GET /v1/stats/weekly` for the same range (e2e).
- Bot replies only to allowlisted chats; a new activity produces exactly one notification even
  if the webhook is delivered twice.
- Compose starts `web` and `bot` alongside the existing services; `make compose-smoke` still passes.
