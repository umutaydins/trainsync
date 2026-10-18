# Phase 6 — Strength training, programs and nutrition

Goal: plan and log gym training (programs, sets, weights, volume, rest) and track food intake
next to the synced Strava data, on the web (phone-first) and in the Telegram bot.

## Tasks
1. Training domain: exercise library, programs, workouts, sets; volume, e1RM and PR math.
2. Training API with idempotent set logging (flaky gym Wi-Fi must not create duplicate sets).
3. Rule-based program generator, progression engine and plate calculator.
4. Nutrition domain and API: foods, food log, daily/weekly summaries, targets, energy balance
   (intake vs BMR + Strava activity calories).
5. BFF write support with CSRF protection.
6. Web: program builder and the active-workout screen (set logging, workout timer, rest timer,
   plate calculator, screen wake lock, installable PWA).
7. Web: training progress, workout history and nutrition pages.
8. Bot: today's workout, quick set and food logging, calorie summary.
9. Daily check-in in Telegram: the bot asks every evening whether you trained, walks through the
   planned exercises (as planned / ±2.5 kg / typed sets), records reasons, sleep, energy, body
   weight, and shows streaks and adherence on the web.

## Acceptance criteria
- `make verify`, `make web-verify`, `make web-e2e` green; CI runs them.
- Logging the same set twice with the same client id stores one set (test).
- Volume, e1RM, plate math and energy balance match hand-computed fixtures.
- Rest timer stays correct after the phone screen locks / tab is backgrounded (timestamp-based, tested).
- Nutrition texts are neutral in every bot tone; no body/weight shaming anywhere (test).

## Evidence

Phase criteria:

| Criterion | Proven by |
|---|---|
| `make verify`, `make web-verify`, `make web-e2e` green; CI runs them | All pass locally on the merged `phase-6` tree on 2026-10-18: `make verify` (lint, mypy strict, 582 unit + 160 integration tests, branch coverage 96% ≥ 85%), `make web-verify` (eslint, `tsc`, 352 vitest tests, `next build`, `check-bundle`), `make web-e2e` (2 Playwright specs) and `make compose-smoke`. `.github/workflows/ci.yml` runs them in the `verify`, `web`, `e2e` and `compose` jobs. **Not run in CI yet**: the branch has not been pushed. |
| Logging the same set twice with the same client id stores one set | `tests/integration/test_training_api.py::test_same_put_twice_and_concurrently_stores_one_set` (201 then 200 with the same body; 5 concurrent PUTs → one row); `tests/integration/test_training_repository.py::test_put_set_is_idempotent_by_client_id`, `::test_concurrent_puts_store_one_set`; web: `web/tests/workout-screen.test.tsx` "a double tap sends one PUT with one client id", "queues a set that got no answer and sends it again, same id, when back online"; bot: `tests/unit/test_bot_training.py::test_repeated_log_delivery_stores_one_set_per_set`, `tests/integration/test_bot_training_api.py::test_redelivered_log_stores_its_sets_once`. ADR 0017 |
| Volume, e1RM, plate math and energy balance match hand-computed fixtures | `tests/unit/test_training_math.py` against `tests/fixtures/training_math.json` (Epley incl. the reps > 12 rule, warm-up exclusion, PRs session by session, weekly volume per muscle); `tests/integration/test_training_api.py::test_progress_endpoints_match_the_training_math`; `tests/unit/test_plates.py` (exact, unreachable → nearest lower + difference, inventory limits, bar heavier than target); `tests/unit/test_energy.py` and `tests/integration/test_nutrition_api.py::test_summaries_and_energy_balance_match_hand_computed_fixture` against `tests/fixtures/nutrition_energy.json`. ADRs 0018, 0019 |
| Rest timer stays correct after the screen locks / the tab is backgrounded | `web/tests/timers.test.ts` "stays correct after the tab is backgrounded for 3 minutes (no interval ticks)", "restores the timer after a reload from localStorage", "alerts once at zero, and not when the tab slept far past it"; `web/tests/workout-screen.test.tsx` "starts the rest timer after a set and keeps it right when the tab was backgrounded", "restores the rest timer and the row ids after a reload". Diagram 20. ADR 0021 |
| Nutrition texts are neutral in every bot tone; no body/weight shaming anywhere | Bot: `tests/unit/test_bot_messages.py::test_packs_have_no_nutrition_or_body_keys`, `::test_neutral_texts_are_the_same_in_every_tone`, `::test_neutral_texts_contain_no_blocked_word`, `::test_packs_contain_no_blocked_word`, `::test_rest_and_sick_answers_are_calm_in_hardcore`; `tests/unit/test_bot_training.py::test_nutrition_and_scale_replies_are_neutral_in_hardcore`. API: `tests/unit/test_energy.py::test_target_warning_is_neutral_and_only_below_bmr`. Web: `web/tests/nutrition-copy.test.tsx` (judgement and body/weight blocklist over the nutrition screens). ADR 0016 |

Task criteria:

| Task | Proven by |
|---|---|
| P6.1 training domain | `tests/integration/test_migrations.py::test_upgrade_downgrade_upgrade_round_trip`, `::test_models_match_migrations`; `tests/unit/test_training_math.py`; `tests/unit/test_exercise_library.py` (unique slugs, known values, every pattern has a bodyweight or dumbbell option); `tests/integration/test_training_repository.py::test_seeded_library_loads` |
| P6.2 training API | `tests/integration/test_training_api.py::test_same_put_twice_and_concurrently_stores_one_set`, `::test_start_from_a_program_day_returns_the_plan_with_last_performance`, `::test_progress_endpoints_match_the_training_math`, `::test_workout_list_is_keyset_paginated`, `::test_programs_crud_and_one_active`, `::test_set_validation`; `tests/unit/test_openapi.py`. ADR 0017 |
| P6.3 generator, progression, plates | `tests/unit/test_generator.py::test_every_combination_gives_a_valid_deterministic_program` (every template × goal × equipment within the time budget, same input → same output); `tests/unit/test_progression.py` (hit → +increment, miss once → hold, miss twice → −10 %); `tests/unit/test_plates.py`. ADR 0018 |
| P6.4 nutrition | `tests/integration/test_nutrition_api.py::test_summaries_and_energy_balance_match_hand_computed_fixture`, `::test_same_food_log_put_twice_stores_one_row`, `::test_barcode_lookup_caches_then_answers_locally`, `::test_lookup_degrades_gracefully_on_timeout`; `tests/unit/test_openfoodfacts_client.py::test_tests_never_point_at_the_real_api`. ADR 0019 |
| P6.5 BFF writes with CSRF | `web/tests/bff-write.test.ts` (wrong/missing Origin or token → 403, correct → forwarded with the key; table of allowed and rejected method + path pairs; traversal; 413/415); `web/tests/csrf.test.ts`; `web/tests/mutate.test.ts`; `web/scripts/check-bundle.mjs`; `scripts/compose_smoke.sh` (CSRF and content-type rejections). ADR 0011 |
| P6.6 workout logger, PWA | `web/tests/timers.test.ts`; `web/tests/workout-screen.test.tsx`; `web/tests/plate-bar.test.tsx` (drawing equals the API answer); `web/tests/retry-queue.test.ts`; `web/tests/wake-lock.test.tsx`; `web/tests/manifest.test.ts`; `web/tests/program-builder.test.tsx`; axe and 375 px in `web/e2e/training.spec.ts`. ADR 0021 |
| P6.7 progress, history, nutrition | `web/tests/training-progress.test.tsx` and `web/tests/nutrition.test.tsx` (charts and cards render the fixture numbers exactly, "unknown" instead of a guess, keyboard-only add-food); `web/e2e/training.spec.ts` (generate → save → activate → workout with 3 sets and the rest timer → finish → history shows the volume; two foods → today's kcal is their sum); screenshots in `docs/img/` |
| P6.8 bot training and nutrition | `tests/unit/test_bot_training.py` (parsers for `/log` and `/eat`: valid, invalid, ambiguous; handlers with the fake Telegram API and a stubbed API; repeated delivery → one set); `tests/integration/test_bot_training_api.py` |
| P6.9 daily check-in | `tests/unit/test_bot_checkin.py` (every path: done with/without program, partly, skipped with/without reason, rest, sick; invalid input re-prompts; as planned / ±2.5 kg sets; stale and double-tapped buttons); `tests/unit/test_checkin_math.py` (streak and adherence fixture; prompt at local time, once, one reminder, DST-safe); `tests/integration/test_checkins.py::test_prompt_once_then_one_reminder`, `::test_duplicate_deliveries_store_one_check_in_and_one_set_each`, `::test_list_and_summary_match_the_fixture`; `web/tests/checkins.test.tsx` (heatmap renders the fixture). ADR 0020 |
| P6.10 gate | This section; `docs/diagrams.md` (training, nutrition and check-in tables in the ER diagram, component diagram, diagrams 17–20); README (screenshots, bot commands, Phase 6 variables, ADRs 0017–0021, Status). "CI green on the PR" is **not met yet**: nothing is pushed. |

## Follow-ups
- Offline-first set logging on the web (P6.6): today failed set `PUT`s wait in a localStorage
  retry queue and are re-sent on reconnect, but the workout page itself needs the network to
  load. A service worker that caches the workout screen plus an IndexedDB queue (Background Sync
  where available) would make a whole session work offline (ADR 0021).
