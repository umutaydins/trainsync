# 0024 — Nightly encrypted pg_dump to iCloud Drive, GFS retention, scripted restore check

- Status: accepted
- Date: 2026-10-18

## Context
The only copy of years of training data lives in a Docker volume on one MacBook. Losing the disk
(or a bad migration) must not lose it. Backups leave the machine, so they must be unreadable to
whoever holds the storage, and a backup that was never restored is a hope, not a backup.
The machine is a 16 GB laptop: whatever runs nightly must be small.

## Decision
- A `backup` service in `compose.prod.yml` (image `deploy/backup/Dockerfile`: pinned
  `postgres:16.15-alpine3.24` + `age`, `bash`, bare `python3`) polls every minute and backs up
  once a day after `BACKUP_TIME` (default 03:30, `BACKUP_TZ` Europe/Istanbul). "Due" means the
  slot has passed and no backup was taken since it, so a Mac that slept through 03:30 backs up
  on wake and a restarted container does not take a second one. `run --rm backup now [label]`
  takes one on demand (P7.5 pre-deploy).
- Format: `pg_dump -Fc | age -r $BACKUP_AGE_RECIPIENT` →
  `trainsync-YYYYMMDD-HHMMSS[-label].dump.age` (UTC) in `BACKUP_DIR`, a bind mount of an
  iCloud Drive folder by default. Written under a dot-name and renamed when complete.
- A `.counts.json` sidecar holds the row count of every public table, counted **in the same
  snapshot** as the dump (one `REPEATABLE READ` transaction exports its snapshot and
  `pg_dump --snapshot` uses it), so the counts describe exactly what the dump contains even
  while webhooks keep writing.
- Retention (`trainsync.ops.retention`, pure and unit-tested): newest per day for the 7 most
  recent days that have a backup, per ISO week for 4 weeks, per month for 6 months; the newest
  is never deleted; unparsable names are never touched; future-dated files are kept. Buckets
  count days *with* a backup, so a two-week outage does not delete everything older.
  Pre-deploy backups (`…-predeploy<sha7>`, P7.5) are outside these buckets: the newest 3 are
  always kept and never stand in for a nightly backup. Before this (amended 2026-10-19) a
  pre-deploy backup could take a day's bucket and push out that night's backup, and an old
  one could be pruned while it was still the restore point of the last rollback.
- Restore check (`backup.sh restore-check`, `scripts/restore-check.sh`, weekly in the loop):
  decrypt fully (age authenticates the file, so truncation or tampering fails here), restore into
  a scratch Postgres started inside the backup container, and compare every table's count with
  the sidecar; exit non-zero on any difference. The weekly result goes to Telegram through the
  stdlib helper `trainsync.ops.alert` (reused by P7.8). CI (`make restore-check-ci`) proves a
  good backup passes and a truncated, altered, wrong-key or count-mismatched one fails.
- The age identity (private key) never sits next to the backups. It lives in the owner's
  password manager; a copy on the Mac (outside iCloud, `chmod 600`) is mounted as a compose
  secret only for the weekly check. Without it backups still run and the check reports "skipped".

## Alternatives considered
- WAL archiving / PITR (pgBackRest, wal-g) — minute-level recovery is not worth a continuously
  running archiver and its storage for a single-user app whose data mostly re-syncs from Strava;
  losing at most a day of manual logs is acceptable. Revisit on a VPS.
- GPG — works, but key management and the CLI are heavier; age has one small static binary,
  public keys that fit in an env var, and authenticated encryption by default.
- Restic/borg to iCloud — deduplication is irrelevant at a few MB per dump, and their
  repositories are many small files that iCloud syncs poorly.
- Comparing counts with the live database — it keeps moving; the snapshot sidecar works offline
  and gives an exact answer.
- Retention in shell — date arithmetic in busybox is error-prone; Python is testable and typed.
  Running the backup from the app image instead would need the PGDG apt repo for a v16 client.

## Consequences
- The backup image adds python3 (~50 MB) to the official Postgres image; `trainsync.ops` must
  stay standard-library only (a unit test enforces it).
- iCloud Drive must keep the folder downloaded ("Optimize Mac Storage" can evict files), and the
  iCloud copy is only as recent as the last sync.
- Losing the age identity makes every backup useless: keep it in two places, neither of them the
  backup folder.
