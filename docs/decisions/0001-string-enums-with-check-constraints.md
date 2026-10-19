# 0001 — String enums with CHECK constraints instead of native Postgres enums

- Status: accepted
- Date: 2026-10-17

## Context
`sync_runs.kind`, `sync_runs.status` and `webhook_events.status` take a small, fixed set of
values. Postgres offers native `ENUM` types, but adding, renaming or removing a value needs
`ALTER TYPE`, which Alembic autogenerate does not track, cannot run inside a transaction on older
versions, and makes downgrades awkward (a value cannot simply be dropped).

## Decision
Store these columns as `VARCHAR(16)` with a named `CHECK (col IN (...))` constraint. The allowed
values live in Python `StrEnum`s (`SyncKind`, `SyncStatus`, `WebhookStatus` in
`trainsync.modules.models`) and the CHECK expression is generated from them.

## Alternatives considered
- Native `ENUM` types — strongest typing, but painful migrations as described above.
- Plain strings without a constraint — easy to migrate, but nothing stops a typo reaching the table.
- A lookup table with an FK — correct, but heavy for three tiny value sets.

## Consequences
- Changing a value set is a regular migration: drop and recreate one CHECK constraint.
- Autogenerate does not detect CHECK expression changes, so whoever edits an enum must write the
  constraint migration by hand (the model-vs-migration test catches table/column drift, not this).
- A few bytes more per row than an enum; irrelevant at this scale.
