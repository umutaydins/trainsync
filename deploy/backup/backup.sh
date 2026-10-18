#!/usr/bin/env bash
# Entrypoint of the backup image (P7.4, ADR 0024).
#
#   backup.sh loop                     daily backup at BACKUP_TIME (BACKUP_TZ) + retention;
#                                      after the backup on RESTORE_CHECK_WEEKDAY, a restore check
#   backup.sh now [LABEL]              one backup + retention now (pre-deploy: `now predeploy`)
#   backup.sh restore-check [FILE]     restore FILE (default: the newest backup) into a scratch
#                                      Postgres inside this container and compare row counts
#   backup.sh prune [--dry-run]        apply retention only
#
# Backups: $BACKUP_DIR/trainsync-YYYYMMDD-HHMMSS[-label].dump.age (pg_dump -Fc, encrypted to
# BACKUP_AGE_RECIPIENT) and a .counts.json sidecar with the row counts of the same snapshot.
# Both are written under a dot-name and renamed when complete, so a half-written file never
# looks like a backup. Connection: the standard PGHOST/PGUSER/PGPASSWORD/PGDATABASE variables.
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/backups}
BACKUP_TIME=${BACKUP_TIME:-03:30}
BACKUP_TZ=${BACKUP_TZ:-Europe/Istanbul}
RESTORE_CHECK_WEEKDAY=${RESTORE_CHECK_WEEKDAY:-7}
BACKUP_POLL_SECONDS=${BACKUP_POLL_SECONDS:-60}
BACKUP_RETRY_SECONDS=${BACKUP_RETRY_SECONDS:-3600}
IDENTITY=${BACKUP_AGE_IDENTITY_FILE:-/run/secrets/backup_identity}
HERE=$(cd "$(dirname "$0")" && pwd)

log() { printf '%s backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
cli() { python3 -m trainsync.ops.backup_cli "$@"; }
# An alert must never fail the job that sends it.
alert() { python3 -m trainsync.ops.alert "trainsync: $*" || true; }

check_recipient() {
  if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; then
    log "BACKUP_AGE_RECIPIENT is not set (the age public key backups are encrypted to)"
    exit 2
  fi
  if ! age -r "$BACKUP_AGE_RECIPIENT" </dev/null >/dev/null 2>&1; then
    log "BACKUP_AGE_RECIPIENT is not a valid age recipient"
    exit 2
  fi
}

has_identity() { [ -r "$IDENTITY" ] && grep -q '^AGE-SECRET-KEY-' "$IDENTITY"; }

backup_now() {
  local label=${1:-} name stem tmp counts_tmp
  check_recipient
  if [ ! -d "$BACKUP_DIR" ] || [ ! -w "$BACKUP_DIR" ]; then
    log "$BACKUP_DIR is not a writable directory"
    return 1
  fi
  # Leftovers of a run that died mid-write (the loop and `now` never run for an hour).
  find "$BACKUP_DIR" -maxdepth 1 -name '.*.partial' -mmin +60 -delete
  name=$(cli name ${label:+--label "$label"}) || return 1
  stem=${name%.dump.age}
  tmp="$BACKUP_DIR/.$name.partial"
  counts_tmp="$BACKUP_DIR/.$stem.counts.json.partial"
  rm -f "$tmp" "$tmp.ok" "$counts_tmp"

  # One REPEATABLE READ transaction exports its snapshot and counts rows in it; pg_dump runs
  # in that same snapshot, so the recorded counts describe exactly what the dump contains.
  if ! BACKUP_TMP=$tmp psql -X -q -At -v ON_ERROR_STOP=1 -v counts_file="$counts_tmp" \
    -v counts_sql="$HERE/counts.sql" <<'SQL'
BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SELECT pg_export_snapshot() AS snapshot \gset
\o :counts_file
\i :counts_sql
\o
\setenv BACKUP_SNAPSHOT :snapshot
\! set -o pipefail; pg_dump -Fc --snapshot="$BACKUP_SNAPSHOT" | age -r "$BACKUP_AGE_RECIPIENT" > "$BACKUP_TMP" && touch "$BACKUP_TMP.ok"
COMMIT;
SQL
  then
    log "psql failed"
    rm -f "$tmp" "$tmp.ok" "$counts_tmp"
    return 1
  fi
  if [ ! -e "$tmp.ok" ] || [ ! -s "$tmp" ] || [ ! -s "$counts_tmp" ]; then
    log "pg_dump | age failed"
    rm -f "$tmp" "$tmp.ok" "$counts_tmp"
    return 1
  fi
  rm -f "$tmp.ok"
  # The sidecar first: the dump appearing under its final name marks the backup complete.
  if ! mv "$counts_tmp" "$BACKUP_DIR/$stem.counts.json" || ! mv "$tmp" "$BACKUP_DIR/$name"; then
    log "could not rename the finished backup"
    return 1
  fi
  log "wrote $name ($(du -k "$BACKUP_DIR/$name" | cut -f1) KiB)"
  # Retention problems are reported but do not make a good backup count as failed.
  cli prune --dir "$BACKUP_DIR" || log "retention failed"
}

# Runs in a subshell so its trap and exported PG* variables stay local.
restore_check() (
  local file=${1:-latest} counts scratch
  if [ "$file" = latest ]; then
    file=$(cli latest --dir "$BACKUP_DIR") || exit 1
  fi
  counts="${file%.dump.age}.counts.json"
  [ -f "$file" ] || { log "restore-check: no such backup: $file"; exit 1; }
  [ -f "$counts" ] || { log "restore-check: missing row-count sidecar: $counts"; exit 1; }
  has_identity || { log "restore-check: no age identity at $IDENTITY"; exit 1; }

  # Every step checks its own status: callers run this inside `if`, where `set -e` is off.
  scratch=$(mktemp -d) || exit 1
  # shellcheck disable=SC2064  # expand $scratch now
  trap "pg_ctl -D '$scratch/data' -m immediate stop >/dev/null 2>&1 || true; rm -rf '$scratch'" EXIT
  initdb -D "$scratch/data" -U postgres -A trust -E UTF8 --no-locale --no-sync >/dev/null \
    || { log "restore-check: initdb failed"; exit 1; }
  pg_ctl -D "$scratch/data" -l "$scratch/postgres.log" -w \
    -o "-c listen_addresses='' -k $scratch -c fsync=off -c shared_buffers=16MB" start >/dev/null \
    || { log "restore-check: scratch Postgres did not start"; exit 1; }
  export PGHOST=$scratch PGPORT=5432 PGUSER=postgres PGDATABASE=restorecheck
  unset PGPASSWORD
  createdb restorecheck || exit 1

  log "restore-check: $(basename "$file")"
  # Decrypt fully first: age authenticates the whole file, so a truncated or altered backup
  # fails here before anything is restored.
  age -d -i "$IDENTITY" -o "$scratch/dump" "$file" \
    || { log "restore-check: decryption failed (wrong identity, truncated or altered file)"; exit 1; }
  pg_restore --no-owner --no-acl --exit-on-error -d restorecheck "$scratch/dump" \
    || { log "restore-check: pg_restore failed"; exit 1; }
  psql -X -q -At -v ON_ERROR_STOP=1 -f "$HERE/counts.sql" >"$scratch/actual.json" \
    || { log "restore-check: counting rows failed"; exit 1; }
  cli compare-counts "$counts" "$scratch/actual.json" || { log "restore-check: FAILED"; exit 1; }
  log "restore-check: OK"
)

weekly_check() {
  local output
  if ! has_identity; then
    log "weekly restore check skipped: no age identity mounted"
    alert "weekly restore check SKIPPED: no age identity mounted (BACKUP_AGE_IDENTITY_FILE)"
    return 0
  fi
  if output=$(restore_check latest 2>&1); then
    log "weekly restore check passed"
    alert "weekly restore check passed. $(printf '%s\n' "$output" | tail -n 1)"
  else
    printf '%s\n' "$output"
    log "weekly restore check FAILED"
    alert "weekly restore check FAILED: $(printf '%s\n' "$output" | tail -n 5)"
  fi
}

loop() {
  local rc=0
  check_recipient
  cli due --dir "$BACKUP_DIR" --at "$BACKUP_TIME" --tz "$BACKUP_TZ" || rc=$?
  if [ "$rc" -eq 2 ]; then
    log "invalid BACKUP_TIME or BACKUP_TZ"
    exit 2
  fi
  trap 'log "stopping"; exit 0' TERM INT
  local identity="not mounted (weekly restore check skipped)"
  if has_identity; then identity=mounted; fi
  log "daily at $BACKUP_TIME $BACKUP_TZ into $BACKUP_DIR; restore check on ISO weekday" \
    "$RESTORE_CHECK_WEEKDAY; age identity $identity"
  while true; do
    if cli due --dir "$BACKUP_DIR" --at "$BACKUP_TIME" --tz "$BACKUP_TZ"; then
      if backup_now; then
        if [ "$(TZ=$BACKUP_TZ date +%u)" = "$RESTORE_CHECK_WEEKDAY" ]; then
          weekly_check
        fi
      else
        log "backup failed; retrying in $BACKUP_RETRY_SECONDS s"
        alert "nightly backup FAILED; retrying in $BACKUP_RETRY_SECONDS s (docker compose logs backup)"
        sleep "$BACKUP_RETRY_SECONDS" &
        wait $! || true
      fi
    fi
    # Short polls instead of one long sleep: a Mac that slept through the slot backs up on wake.
    sleep "$BACKUP_POLL_SECONDS" &
    wait $! || true
  done
}

case "${1:-loop}" in
  loop) loop ;;
  now) backup_now "${2:-}" ;;
  restore-check) restore_check "${2:-latest}" ;;
  prune) shift; cli prune --dir "$BACKUP_DIR" "$@" ;;
  *)
    echo "usage: backup.sh loop | now [LABEL] | restore-check [FILE] | prune [--dry-run]" >&2
    exit 2
    ;;
esac
