# 0020 — Daily check-in: streaks, adherence, scheduler bookkeeping, conversation state

- Status: accepted
- Date: 2026-10-18

## Context
P6.9 adds an evening question in Telegram — did you train today? — answered with buttons and
short replies, stored in the app and shown on the web. Four things needed a definition that the
task left open: what a streak and adherence mean, how the worker knows it has already asked
(across restarts and overlapping cron runs), where the conversation keeps its state, and how a
redelivered Telegram update or a double tap stays harmless. Days must be the owner's days: at
00:30 in Istanbul "today" is already tomorrow, while the rest of the API counts UTC days.

## Decision
- **Local days.** Check-ins are stored per local date in `CHECKIN_TZ` (default
  `Europe/Istanbul`). The bot uses the same zone for "today" in `/log`, `/eat`, `/kcal` and
  `/weight` and sends that date to the API explicitly.
- **Streak** = consecutive days with a check-in whose status is not `skipped`. Done, partial,
  rest and sick/injured all count: the habit is showing up honestly, and a rest or sick day must
  not punish anyone. A missing day or a skip ends it. The current streak runs up to today, or up to
  yesterday while today has no check-in yet (the day is not over).
- **Adherence** = planned days done / planned days over a range, computed per ISO week: planned
  = `min(days_per_week of the active program, days of that week inside the range − sick/injured
  days)`, never below 0; done = done + partial days, capped at planned. No active program →
  nothing is planned and adherence is `null`, not 0 %. Programs have no history, so past weeks
  use today's active program. Default range: the current ISO week and the three before it.
- **Scheduler.** A worker cron every 5 minutes decides by itself (pure `decide()` with an injected
  clock): at or after `CHECKIN_TIME` on the local date — the instant is computed per local date
  with `zoneinfo`, so it stays 21:00 on the wall clock across DST — send the prompt if that date
  has no check-in and no prompt was sent; `CHECKIN_REMINDER_MINUTES` after the prompt, still
  unanswered, send one reminder; then nothing until the next date. "Sent" is a claim in the
  existing `notifications` table (`checkin_prompt` / `checkin_reminder`, `object_id` = local
  date as `yyyymmdd`, ADR 0012's claim → send → release-on-failure; the new kinds widen the
  CHECK constraint in migration 0007, ADR 0001). Postgres instead of Redis keys because the
  answer to "did we ask?" must survive a Redis flush as well as a worker restart, and the
  check-in it is compared with lives in Postgres too.
- **Conversation state** in Redis, `checkin:{chat}:{yyyymmdd}`, TTL 6 h: a small JSON state
  machine (state diagram 17 in `docs/diagrams.md`), so a bot restart mid-flow continues where it
  was. Every transition increments `seq`; every button carries `ci:{yyyymmdd}:{seq}:{action}`.
  A press whose date is not today or whose `seq` is not the current one is answered with a toast
  ("that button belongs to an earlier question") and changes nothing — this covers old
  messages, double taps and redelivered callback updates. A text answer carries its Telegram
  `update_id`; one at or below the last handled id is a redelivery and is ignored.
- **Idempotent writes.** The check-in is `PUT /v1/checkins/{date}` (upsert by date, every field
  replaced). Sets use `uuid5("checkin:{date}:{exercise_id}:{set_index}")` (ADR 0017), so Edit,
  a retry or a redelivery rewrites the same rows. The status is stored as soon as it is chosen,
  so the reminder never fires for an answered day even if the rest of the flow is abandoned.
- **"As planned"** logs the planned number of sets at the suggested weight with the **bottom**
  of the rep range. Logging the top would tell double progression (ADR 0018) to add weight every
  session the owner taps the button; the bottom keeps the suggestion at "hold" until real reps are
  typed. ±2.5 kg logs the same with the weight changed.
- **Tone.** Training wording comes from the tone packs; only "skipped with no reason" may push in
  the hardcore tone. Rest and sick/injured replies are calm in every tone (a test checks the
  hardcore wording for profanity), and scale, sleep and energy questions come from the tone-free
  layer, like nutrition (P6.8).

## Alternatives considered
- Redis keys for "prompt sent" — simpler, but a flushed or replaced Redis would re-send, and the
  claim/release pattern already exists in Postgres.
- An arq job scheduled at the exact prompt time — arq crons are fixed UTC minutes, a DST change
  would shift it by an hour, and a worker that is down at 21:00 would never send. A frequent tick
  that decides is restart- and DST-proof.
- Counting rest days as breaks in the streak — punishes recovery, which the owner explicitly does
  not want.
- Storing the conversation in Postgres — durable beyond what a 6-hour chat needs, and it would
  mean a table for transient UI state.

## Consequences
- The worker needs the bot token and chat id (it already had them for notifications).
- Adherence for past weeks changes when the active program changes; the summary says which
  `days_per_week` it used.
- Logging fewer sets on Edit than the first time leaves the extra sets in the workout; they can
  be removed on the web.
- A Telegram reply to a prompt older than the state TTL (6 h) starts a fresh flow; a status button
  from an earlier day is always stale.
