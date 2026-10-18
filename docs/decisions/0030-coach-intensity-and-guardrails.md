# 0030 — Coach intensity (savage), timed coach messages and hard guardrails

- Status: accepted
- Date: 2026-10-19

## Context
The hardcore tone (ADR 0016) allows only mild swearing and only reacts when asked. The owner
wants a much harder coach that he opts into himself: unrestricted Turkish profanity, brutal
roasting of excuses and missed work, and messages at the right moments (before and during a
planned workout, between sets, at the end). Harsh is fine; harmful is not: some lines must hold
no matter what he configures.

## Decision
- **Intensity is a separate axis from tone.** `BOT_INTENSITY=normal|savage` (default `normal`).
  `savage` takes effect with `BOT_TONE=hardcore` and `BOT_LANG=tr`; other combinations fall back
  to the existing packs. (Since [ADR 0031](0031-runtime-bot-language.md): with `BOT_TONE=hardcore`
  in either language; the chat's `/lang` choice picks savage/tr or savage/en.) It is an explicit opt-in that the owner sets in `.env.prod` himself, and
  the assistant's system prompt says so. `/yumusak` sets a Redis key (`coach:soft_until`, 24 h)
  read by both bot and worker; while it is set the effective intensity is `normal`; `/sert`
  deletes it.
- **Savage lines are categories, not keys.** `src/trainsync/coach/savage_tr.py` holds original
  lines per category (`excuse`, `missed_workout`, `under_target`, `workout_start`, `rest_over`,
  `workout_done_good`, `workout_done_bad`, `reminder_before`, `reminder_now`, `escalation`) plus
  `punchline_en`. A line is chosen at random among those not used in the last 10 sends of that
  category (Redis list per category, shared by bot and worker); about 1 in 4 savage messages gets
  a punchline appended. An optional, git-ignored `config/messages.local.yaml` adds the owner's own
  lines per category; they are merged in and sent verbatim.
- **Guardrails are code, not style.** `src/trainsync/coach/guardrails.py`:
  - an injury/illness detector (pain, injury, illness, dizziness, chest pain, fainting, fever, …,
    Turkish and English) runs on every chat message first, in every tone and intensity; a hit
    gets a calm "rest / see a doctor" reply from the neutral layer and nothing else: no roast, no
    push, no assistant call;
  - a blocklist of body/weight/appearance words, identity slurs (ethnicity, religion, sexual
    orientation, disability, gender) and calorie-punishment phrases ("burn it off", "aç kal", skip
    meals). Built-in lines are tested against it; local lines that hit it are dropped with a log
    line (never altered); an assistant reply that hits it is replaced by a neutral fallback.
    Profanity is not on the list and is never filtered;
  - food rule (replaced by [ADR 0032](0032-food-roast-profanity-level-and-distress.md)): in
    savage the coach roasts unhealthy *choices* (junk, sugar, alcohol, cigarettes, staying up
    late, high-sugar logs), never the body, then gives one concrete move (smaller portion, a
    swap, log it now) with the day's target unchanged; no message suggests skipping meals,
    compensating or eating below the nutrition target. The first version roasted no food at all
    ("eat it, log it, stay in your daily target");
  - distress (guilt spiral, purging, not eating, self-hate, binge talk) gets a calm reply like
    pain does, in every mode (ADR 0032).
- **Timed messages run in the worker**, like the check-in (ADR 0020): a cron every minute for the
  schedule-based reminders, and jobs enqueued by the API when a workout starts, a set is logged
  (rest over, under target) and a workout finishes. Every send claims a `notifications` row first
  (new kinds, object id = local date or workout/set id), so retries and restarts never repeat a
  message. Nothing proactive is sent in `QUIET_HOURS` (default 23:00–07:00, local), and a
  reminder whose moment fell in quiet hours is skipped, not delayed. Replies to the owner's own
  messages are not proactive and are always answered.
- **Schedule.** Program days get an optional `weekday` (0 = Monday) and `start_time`. Days
  without a weekday follow a default spread by `days_per_week` (e.g. 3 → Mon/Wed/Fri, 4 →
  Mon/Tue/Thu/Fri); a missing start time is `WORKOUT_REMINDER_TIME` (18:00). Stages relative to
  the start: −30 min, 0, +30, +90 (nudges) and +180 ("missed"); all stop once any workout was
  started that local day.
- **Underperformance is measured, not guessed**: a set is under target when its reps are below
  the planned `rep_min` at the planned/suggested weight or its weight is below the suggested
  weight (ADR 0018); a finished workout is "bad" when planned sets are missing or any set was
  under target, "good" otherwise (PRs listed from the workout's records).

## Alternatives considered
- Let the LLM write every coach message — needs an API key and costs per message, the reminders
  must work without one, and guardrails on generated text are weaker than on reviewed lines.
- Make savage a third tone — tone and intensity change independently (savage only exists in
  Turkish, and soft mode must drop intensity without changing the language or the tone).
- Filter profanity in savage — the owner asked for it explicitly; the guardrails target harm
  (body, identity, health, food restriction), not words he chose. (ADR 0032 adds a per-chat
  profanity level: `max` swears in every savage message.)

## Consequences
- The bot sends more messages; quiet hours, soft mode and the per-stage idempotency keep that
  bounded. The schedule defaults may not match the owner's week until he sets weekdays/start
  times on his program days through the API.
- The blocklist is a backstop for lines and generated replies, not a guarantee; the built-in
  lines are reviewed, and the injury detector errs on the side of stopping the roast.
- `BOT_INTENSITY` is read by bot and worker (compose passes it through), the local line file is
  mounted read-only into both.
