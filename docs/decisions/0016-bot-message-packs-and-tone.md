# 0016 — Bot wording in message packs per tone and language

- Status: accepted
- Date: 2026-10-18

## Context
The bot's replies, the new-activity notification and the assistant's canned answers were English
string literals spread over `formatting.py`, `handlers.py` and `assistant.py`. The owner wants a
Turkish bot and an optional "hardcore" tone: a tough-love running coach who reacts to the week's
training instead of only reporting it. Wording and numbers must not drift apart, and the tone
must never turn into insults.

## Decision
- `BOT_TONE` (`neutral` default, `hardcore`) and `BOT_LANG` (`en` default, `tr`) pick one of four
  packs in `src/trainsync/modules/coach/packs/`. A pack maps every `Key` to one or more `str.format`
  templates, plus month and weekday short names. `formatting.py` still computes every number
  (km, durations, pace, percentages); packs only own the words around them.
- `Messages` renders a key; with several variants it picks one with an injected
  `random.Random`, so tests seed it and get deterministic text. Production uses an unseeded one.
- The coach's week verdict is a function of the numbers, `formatting.week_verdict`, and compares
  **moving time** (not distance), so a week of rides and a week of runs compare fairly:
  - this week and last week both without activities → ask whether it is injury or rest, no push;
  - under 50% of last week → push hard; 50–99% → keep going; 100% and more → acknowledge, then
    raise the bar.
  "This week" is the ISO week so far, like `/week`. Neutral packs define the verdict keys as an
  empty template, which means "no line": neutral output is unchanged.
- The persona is original ("Coach" / "Koç"): short, blunt sentences; mild profanity only (damn,
  hell, crap; lan, ulan, hassiktir); effort and consistency only, never body, weight,
  appearance or identity; no real person named or quoted.
- The assistant's system prompt takes the same switch: a persona paragraph per tone and a
  "Reply in English/Turkish" line per language. It lives in `assistant.py`, not in the packs: it
  is an instruction to the model, not text a user reads.
- CI guards: every pack defines every key and only uses its key's fields; a snapshot per
  tone × language (`tests/unit/modules/coach/packs/snapshots/bot_messages/`); a blocklist of slurs, insults, stronger
  profanity and body/weight words that no pack may contain.

## Alternatives considered
- gettext / `.po` catalogues — the standard for translation, but tone is not a language, the
  variants and the empty-means-no-line rule do not fit, and it adds a compile step for 4 small
  files.
- Let Claude write every reply in the chosen tone — numbers stay deterministic only for the
  commands if the model never touches them; it adds cost, latency and a dependency on an API key
  to commands that work offline today.
- Compare distance for the verdict — matches the "Distance ± km" line, but a swim week would
  always look like a collapse next to a ride week.

## Consequences
- A new message needs a `Key`, its fields in `FIELDS`, and a template in all four packs; the
  completeness test fails until all four have it.
- The blocklist is a backstop, not a guarantee: it cannot catch every insult, so new hardcore
  wording still needs a human read. Snapshot diffs make that read easy.
- The verdict compares a partial week with a full one, so early in the week the coach pushes
  more often. That is deliberate (it is a nudge, and `/week` shows the real numbers), and it is
  what the owner asked for.
- Turkish packs keep the decimal point (`41.3 km`) for consistency with the API and the
  dashboard.
