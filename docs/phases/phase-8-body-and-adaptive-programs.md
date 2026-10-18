# Phase 8 — Body composition, Apple Health and adaptive programs

Goal: body measurements flow in automatically (Xiaomi S400 → Xiaomi Home → Apple Health →
iOS Shortcut → trainsync), and programs and nutrition targets adapt to measured progress through
proposals the owner approves — rule-based by default, LLM-assisted only when an API key exists.

## Tasks
1. Body measurements model (weight, body fat, lean mass, height; source; trend weight; goals).
2. Apple Health ingest endpoint with a scoped token + step-by-step iOS Shortcut guide.
3. Apple Health `export.zip` history import (streaming, background job).
4. Program versioning: every manual or automatic change is a version with a diff; revert.
5. Adaptive training engine: weekly review → proposals with reasons; approve/reject; optional
   auto-apply for minor changes.
6. Adaptive nutrition targets from intake + trend weight, with hard guard rails.
7. Optional LLM layer that drafts and explains proposals, always validated by the rules.
8. Web progress hub: body composition charts, goals, relative strength, program timeline,
   proposals inbox with diff view.
9. Bot: weekly review with approve/reject buttons; neutral body-data messages.

## Acceptance criteria
- Shortcut payload sent twice stores each sample once (test); `export.zip` of 100k records
  imports in bounded memory (test with generated fixture).
- Trend weight, TDEE estimate and proposals match hand-computed fixtures.
- No program or target changes without approval unless auto-apply is enabled and the change is
  classified minor (test). Every change is versioned and revertible (test).
- Calorie targets never below BMR, deficit ≤ 25 %, planned loss ≤ 0.75 % body weight/week (tests).
