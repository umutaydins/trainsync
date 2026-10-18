# 0032 — Food roast, a per-chat profanity level, distress guardrails

- Status: accepted
- Date: 2026-10-19
- Amends: [ADR 0030](0030-coach-intensity-and-guardrails.md) (the food rule)

## Context
In savage mode (ADR 0030) the owner wants the coach to go after unhealthy choices too (junk food,
sugar, alcohol, cigarettes, staying up late), where the first version only answered cravings
with "eat it, log it, stay in your daily target". He also wants a stronger dial: swearing in every
savage message, not only in the roast lines, switchable from the chat like `/lang` (ADR 0031).
A harder coach needs firmer exits: talk of guilt, purging, not eating, self-hate or bingeing must
never be roasted or sworn at.

## Decision
- **Food rule (replaces "food is never roasted").** In savage mode the coach roasts the *choice*,
  never the person's body: a `food_roast` line, then exactly one concrete move for that kind of
  choice (smaller portion, a better swap, "log it now", phone away and lights out), then the
  day's kcal target unchanged. Triggers: chat mentions of junk (sweets and sugar, soft and energy
  drinks, fast food, fried food, alcohol, cigarettes, vaping) or of staying up late
  (`guardrails.food_kind`), and `/eat` logs of an item with more than 22.5 g sugar per 100 g
  (the UK front-of-pack "high" mark) or NOVA group 4, plus a day whose sugar total passes
  `SUGAR_LIMIT_G` (50 g, the WHO "free sugars" figure at 2,000 kcal). Total sugars over-count
  fruit and milk sugar; for a roast trigger that is acceptable. The moves never suggest
  skipping, compensating or eating below the target, and the blocklist now also catches "eat
  less", "eat below …" and punishment cardio.
- **Sugar and NOVA are stored.** `foods` and `food_logs` get `sugars_100g` and `nova_group`
  (migration 0013, nullable: unknown stays unknown); logs snapshot them like the macros (ADR
  0019), Open Food Facts fills them, the day summary gains `sugars_g` (known values only).
- **Profanity is a third axis**, next to tone and intensity: `BOT_PROFANITY=roast|max`,
  default `roast`, and a per-chat override in `chat_settings.profanity` (migration 0012; `lang`
  becomes nullable so either setting can exist alone). `PUT /v1/chats/{id}/settings` takes either
  field and keeps the other. `/swear` (buttons) and `/swear max|roast` set it; it only matters
  while savage is in effect (configured and not in `/yumusak`).
- **How max reaches every message.** Savage lines have a `max` variant per category (separate
  pools, at least as many lines as the roast pool, the local file's `max:` section). Every other
  message (tone-pack replies, the neutral layer, check-in, summaries, errors) gets a rotated
  `max_opener` line in front of it at send time: one place in the bot (`Dispatcher._send`) and one
  per worker sender. A message that already contains a savage line is left alone, so nothing gets
  two. Writing max wording for each of the ~170 pack keys was rejected: four times the text to
  review, and a message assembled from several keys would swear once per key.
- **The assistant** gets "swear naturally in every reply, neutral answers and praise included"
  in max; its replies are not given an opener (the model swears in its own words).
- **Distress overrides everything.** `guardrails.mentions_distress` (guilt spiral, threw up or
  purged, haven't eaten all day, self-hate, binge talk; tr and en) is checked before pain, pain
  before any trigger. Both get a calm reply from the neutral layer, marked so that max never
  adds an opener, and no assistant call. Distress beats pain because "kustum" after a binge needs
  the supportive reply, not "see a doctor".
- **Unknown commands** answer in the current tone and point to `/help`: the tone pack's line,
  or an `unknown_command` savage line plus the pointer.

## Alternatives considered
- Swear words spliced into the tone packs' templates in max — breaks the field contracts of the
  templates and still needs per-key review in two languages.
- Let the assistant write every max message — reminders must work without an API key and the
  guardrails on reviewed lines are stronger than on generated ones (ADR 0030).
- Per-chat intensity instead of a profanity level — the owner asked for swearing as its own dial;
  soft mode keeps dropping both together.
- A sugar threshold per drink (11.25 g / 100 ml) — OFF data does not say reliably whether a value
  is per 100 ml; NOVA 4 and the chat triggers catch soft drinks anyway.

## Consequences
- In max the bot is crude everywhere, by the owner's choice; `/swear roast` or `/yumusak` turn it
  down from the chat. Calm replies to pain and distress never swear.
- Roasting food choices is a deliberate exception to "never comment on food" for savage only; the
  guardrails that protect against restriction (no skipping, no compensation, the target stays)
  are code and tested, and distress talk exits to the calm reply.
- The sugar trigger is only as good as the data: foods without a sugar value are never roasted
  for sugar.
