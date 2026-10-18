# 0018 — Rule-based programs; LLM optional on top

- Status: accepted
- Date: 2026-10-18

## Context
"Give me a 4-day upper/lower hypertrophy program for a gym with barbells and dumbbells" should
produce a sensible program. After that, each session should suggest the next weights, and the app
should say which plates to load. An LLM could write programs, but its output changes between
calls, is hard to test, costs money, may name exercises that are not in the library, and would
need the network in the gym.

## Decision
- `training/generator.py` is a pure, deterministic function of the request and the exercise
  library:
  - Templates: full body (2–3 days, A/B/C), upper/lower (4: A/B), push/pull/legs (3 or 6: A, or
    A and B). The default is picked by days per week.
  - A day is a list of slots: movement pattern, role (compound or accessory), variant. A slot
    takes the n-th library exercise of that pattern that the equipment allows. Bodyweight is
    always allowed. Compounds prefer barbell > dumbbell > machine > kettlebell > cable >
    bodyweight > band; accessories prefer dumbbell and cable. Ties go by id. Variants make A and
    B days differ, and an exercise is used at most once per day.
  - Dose by goal: strength 5/4 × 3–6 at 180 s (accessories 3 × 6–10 at 90 s); hypertrophy 4/3 ×
    8–12 at 90 s (accessories 3 × 10–15 at 60 s); general 3 × 8–12 at 75 s (accessories 3 ×
    10–15 at 60 s). The first number is for the day's first compound.
  - Time is estimated as 60 s set-up + 45 s per set + rest between sets. Until the day fits
    `session_minutes` (minimum 20), the generator drops accessories (last first), cuts compound
    sets to 3, drops compounds (always keeping one), and finally cuts sets down to 1.
- `POST /v1/training/programs/generate` returns a **preview** and saves nothing. Its `program`
  field is a ready body for `POST /v1/training/programs`, so the user can edit it and saving
  goes through the one validated path. No `?save=true` shortcut.
- `training/progression.py` uses double progression on the working sets of the last two
  sessions:
  - every set reached `rep_max` (and at least the planned number of sets) → +2.5 kg (+5 kg
    for lower-body primary muscles; `PROGRESSION_INCREMENT_KG`,
    `PROGRESSION_LOWER_BODY_INCREMENT_KG`);
  - two sessions in a row with a set below `rep_min` → −10 %, rounded down to 1.25 kg;
  - otherwise hold.
  No history gives the planned start weight. Progression `none` and bodyweight (0 kg) hold.
  The suggestion is returned with each planned exercise when a workout starts and when it is
  fetched.
- `training/plates.py` does an exact bounded search, not a greedy one, over the inventory
  (`GYM_PLATES`, counted in pairs). It finds the heaviest weight that is at most the target,
  using the fewest plates (heavier plates win ties). If the target cannot be made, it returns
  the nearest lower weight and the difference.

## Alternatives considered
- LLM-generated programs: nondeterministic, cannot be tested by property, costs money, and
  needs a network. It can come later on top, as an assistant that edits a generated preview
  before it is saved through the same endpoint.
- Percentage-based programs (e.g. 5/3/1): they need a tested 1RM per lift, which a new user does
  not have. Double progression only needs the last sessions.
- Greedy plate loading: wrong with a limited inventory (25×1 + 15×2 per side cannot make 30 kg
  greedily).

## Consequences
- Every template × goal × equipment × duration combination is checked by a unit test
  (`tests/unit/test_generator.py`), and the same input always gives the same program.
- Adding an exercise to the library can change which exercise a slot picks. That is fine: saved
  programs keep their exercise ids.
- The time estimate is rough. It keeps sessions near the target, but it is not a promise.
