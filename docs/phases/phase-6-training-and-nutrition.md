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

## Follow-ups
- Offline-first set logging on the web (P6.6): today failed set `PUT`s wait in a localStorage
  retry queue and are re-sent on reconnect, but the workout page itself needs the network to
  load. A service worker that caches the workout screen plus an IndexedDB queue (Background Sync
  where available) would make a whole session work offline (ADR 0020).
