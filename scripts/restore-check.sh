#!/usr/bin/env bash
# Restore check of the production backups (P7.4, ADR 0024). Decrypts a backup with the age
# identity, restores it into a scratch Postgres inside the backup image and compares the row
# count of every table with the .counts.json sidecar recorded at backup time. Exits non-zero
# on a decryption error, a failed restore or any count mismatch.
#
#   scripts/restore-check.sh                                # newest backup in BACKUP_HOST_DIR
#   scripts/restore-check.sh PATH/trainsync-….dump.age      # one file (its sidecar next to it)
#   scripts/restore-check.sh --identity KEY.txt [PATH]      # identity other than the configured one
#
# Reads .env.prod (ENV_FILE overrides) and uses the backup image of compose.prod.yml, so it
# needs no local Postgres or age. The live database is not touched. The image tag is the one
# `scripts/mac-prod.sh tag` resolves (TRAINSYNC_TAG, the env file, the last deploy, the running
# stack, the git SHA), so TRAINSYNC_TAG need not be set.
set -euo pipefail
cd "$(dirname "$0")/.."

env_file=${ENV_FILE:-.env.prod}
TRAINSYNC_TAG="$(TRAINSYNC_ENV_FILE="$env_file" scripts/mac-prod.sh tag)"
export TRAINSYNC_TAG
args=(docker compose --env-file "$env_file" -f compose.prod.yml run --rm --no-deps)

if [ "${1:-}" = "--identity" ]; then
  [ $# -ge 2 ] || { echo "usage: $0 [--identity FILE] [BACKUP]" >&2; exit 2; }
  identity="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
  args+=(-v "$identity:/run/secrets/restore_identity:ro")
  args+=(-e BACKUP_AGE_IDENTITY_FILE=/run/secrets/restore_identity)
  shift 2
fi

target=latest
if [ $# -gt 0 ]; then
  dir="$(cd "$(dirname "$1")" && pwd)"
  args+=(-v "$dir:/restore:ro")
  target="/restore/$(basename "$1")"
fi

"${args[@]}" backup restore-check "$target"
