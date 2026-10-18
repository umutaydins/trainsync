#!/usr/bin/env bash
# One-command deploy and rollback of the production stack on the Mac (P7.5, ADR 0026).
#
#   scripts/deploy.sh deploy               ship origin/main (clean main, green CI) to the Mac
#   scripts/deploy.sh rollback             back to the previous deploy's images
#   scripts/deploy.sh rollback --restored  same, after the database was restored from the
#                                          pre-deploy backup (skips the migration check)
#   scripts/deploy.sh status               the recorded current and previous deploy
#
# deploy: refuse unless the worktree is clean, the branch is main and HEAD == origin/main after a
# fetch, and CI succeeded for that SHA (gh). Then: build images tagged with the SHA, take a
# pre-deploy backup, record the Alembic revision, run migrations as the one-shot migrate
# container, `up -d`, smoke test (gateway /health/ready, one /v1 call, Telegram getMe). A failed
# smoke test rolls back automatically.
# rollback: if the deploy being undone crossed migrations, all of them must declare
# `reversible = True` (scripts/migration_reversibility.py); they are downgraded with the new
# image before the previous images start. Otherwise it refuses and prints the restore steps.
#
# Every external command (git, gh, docker, curl, sleep, python3) is looked up on PATH, so the
# tests run this script against stubs. Overridable settings:
#   TRAINSYNC_ENV_FILE   default <repo>/.env.prod
#   TRAINSYNC_STATE_DIR  default ~/Library/Application Support/trainsync (deploy-state)
#   TRAINSYNC_LOG_DIR    default ~/Library/Logs/trainsync (deploys.log)
#   TRAINSYNC_PYTHON     default python3;  GATEWAY_PORT default from the env file, else 8080
#   TRAINSYNC_MIGRATIONS_DIR  default <repo>/migrations/versions
#   SMOKE_ATTEMPTS (30), SMOKE_INTERVAL_SECONDS (2)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${TRAINSYNC_ENV_FILE:-$ROOT/.env.prod}"
COMPOSE_FILE="$ROOT/compose.prod.yml"
STATE_DIR="${TRAINSYNC_STATE_DIR:-$HOME/Library/Application Support/trainsync}"
STATE_FILE="$STATE_DIR/deploy-state"
LOG_DIR="${TRAINSYNC_LOG_DIR:-$HOME/Library/Logs/trainsync}"
DEPLOY_LOG="$LOG_DIR/deploys.log"
PYTHON="${TRAINSYNC_PYTHON:-python3}"
MIGRATIONS_DIR="${TRAINSYNC_MIGRATIONS_DIR:-$ROOT/migrations/versions}"
SMOKE_ATTEMPTS="${SMOKE_ATTEMPTS:-30}"
SMOKE_INTERVAL_SECONDS="${SMOKE_INTERVAL_SECONDS:-2}"
LOCK_DIR="$STATE_DIR/deploy.lock"

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
}

say() { echo "deploy: $*"; }

# One line per deploy or rollback: timestamp, action, sha, result[, detail].
log_line() {
  mkdir -p "$LOG_DIR"
  printf '%s %s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${2:-unknown}" "$3" >>"$DEPLOY_LOG"
}

# Value of KEY in the env file (last assignment wins, surrounding quotes stripped), or empty.
env_value() {
  local line
  [ -f "$ENV_FILE" ] || return 0
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  printf '%s' "$line"
}

# Value of KEY in the state file, or empty.
state_value() {
  [ -f "$STATE_FILE" ] || return 0
  grep -E "^$1=" "$STATE_FILE" | tail -n 1 | cut -d= -f2- || true
}

write_state() {
  # $1 current_sha  $2 current_tag  $3 current_rev  $4 previous_sha  $5 previous_tag
  # $6 previous_rev (rollback target revision)  $7 backup label
  mkdir -p "$STATE_DIR"
  {
    echo "current_sha=$1"
    echo "current_tag=$2"
    echo "current_rev=$3"
    echo "previous_sha=$4"
    echo "previous_tag=$5"
    echo "previous_rev=$6"
    echo "backup_label=$7"
    echo "updated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$STATE_FILE.tmp"
  mv "$STATE_FILE.tmp" "$STATE_FILE"
}

# compose with an explicit tag: compose TAG args...
compose() {
  local tag="$1"
  shift
  TRAINSYNC_TAG="$tag" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

# The revision the database is at, as `alembic current` in the migrate container of TAG reports
# it ("base" for an empty database).
alembic_current() {
  local out
  out="$(compose "$1" --profile migrate run --rm -T migrate alembic current)" || return 1
  printf '%s\n' "$out" | tr -d '\r' | awk '
    $1 ~ /^[A-Za-z0-9_]+$/ && (NF == 1 || $2 == "(head)") { rev = $1 }
    END { print (rev == "" ? "base" : rev) }'
}

# Tag of the running api container (for the first deploy, before any state exists).
running_tag() {
  local image
  image="$(compose unknown ps --format '{{.Image}}' api 2>/dev/null | head -n 1 || true)"
  case "$image" in
    trainsync:*) printf '%s' "${image#trainsync:}" ;;
  esac
}

# Telegram message on success/failure; never fails the caller. The token goes to curl through
# a config on stdin, never on the command line.
alert() {
  local token chat
  token="$(env_value TELEGRAM_BOT_TOKEN)"
  chat="$(env_value TELEGRAM_NOTIFY_CHAT_ID)"
  if [ -z "$chat" ]; then
    chat="$(env_value TELEGRAM_ALLOWED_CHAT_IDS)"
    chat="${chat%%,*}"
  fi
  [ -n "$token" ] && [ -n "$chat" ] || return 0
  printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$token" \
    | curl -fsS --max-time 10 -o /dev/null -K - \
      --data-urlencode "chat_id=$chat" --data-urlencode "text=trainsync: $*" \
    || echo "deploy: Telegram alert failed (ignored)" >&2
}

# ------------------------------------------------------------------------------------- smoke

smoke() {
  local port base key token attempt=1
  port="${GATEWAY_PORT:-$(env_value GATEWAY_PORT)}"
  base="http://127.0.0.1:${port:-8080}"
  until curl -fsS --max-time 5 -o /dev/null "$base/health/ready"; do
    if [ "$attempt" -ge "$SMOKE_ATTEMPTS" ]; then
      say "smoke: $base/health/ready not ready after $SMOKE_ATTEMPTS attempts"
      return 1
    fi
    attempt=$((attempt + 1))
    sleep "$SMOKE_INTERVAL_SECONDS"
  done
  say "smoke: /health/ready ok"

  key="$(env_value API_KEYS)"
  key="${key%%,*}"
  if [ -z "$key" ]; then
    say "smoke: no API_KEYS in $ENV_FILE"
    return 1
  fi
  if ! printf 'header = "X-API-Key: %s"\n' "$key" \
    | curl -fsS --max-time 10 -o /dev/null -K - "$base/v1/sync/status"; then
    say "smoke: GET /v1/sync/status failed"
    return 1
  fi
  say "smoke: /v1/sync/status ok"

  token="$(env_value TELEGRAM_BOT_TOKEN)"
  if [ -n "$token" ]; then
    if ! printf 'url = "https://api.telegram.org/bot%s/getMe"\n' "$token" \
      | curl -fsS --max-time 10 -o /dev/null -K -; then
      say "smoke: Telegram getMe failed"
      return 1
    fi
    say "smoke: Telegram getMe ok"
  fi
}

# ------------------------------------------------------------------------------------ deploy

lock() {
  mkdir -p "$STATE_DIR"
  mkdir "$LOCK_DIR" 2>/dev/null || {
    say "another deploy or rollback is running (remove $LOCK_DIR if it is stale)"
    exit 1
  }
  trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
}

refuse() {
  say "refused: $2"
  log_line deploy "$1" "refused: $2"
  exit 1
}

# A step of the deploy failed before the new containers started: the old ones still run.
abort() {
  say "FAILED: $2 (the previous version keeps running)"
  log_line deploy "$1" "failed: $2"
  alert "deploy of $1 failed: $2; the previous version keeps running"
  exit 1
}

preflight() {
  local branch head remote
  cd "$ROOT"
  [ -f "$ENV_FILE" ] || refuse unknown "$ENV_FILE is missing"
  [ -z "$(git status --porcelain)" ] || refuse unknown "the worktree has uncommitted changes"
  branch="$(git rev-parse --abbrev-ref HEAD)"
  [ "$branch" = main ] || refuse unknown "on branch '$branch', not main"
  git fetch --quiet origin main || refuse unknown "git fetch origin main failed"
  head="$(git rev-parse HEAD)"
  remote="$(git rev-parse origin/main)"
  [ "$head" = "$remote" ] || refuse "$head" "HEAD $head is not origin/main $remote (git pull --ff-only)"
}

check_ci() {
  local sha="$1" result
  result="$(gh run list --commit "$sha" --workflow ci --limit 1 --json status,conclusion \
    --jq '.[0] | "\(.status) \(.conclusion)"' 2>/dev/null)" \
    || refuse "$sha" "could not read CI runs for $sha (gh auth status)"
  case "$result" in
    "completed success") say "CI is green for $sha" ;;
    "" | "null null") refuse "$sha" "no CI run for $sha" ;;
    *) refuse "$sha" "CI for $sha is '$result', not 'completed success'" ;;
  esac
}

cmd_deploy() {
  local sha tag label rev_before rev_after prev_sha prev_tag prev_rev
  preflight
  sha="$(git rev-parse HEAD)"
  check_ci "$sha"
  lock
  tag="${sha:0:12}"
  label="predeploy${sha:0:7}"

  prev_sha="$(state_value current_sha)"
  prev_tag="$(state_value current_tag)"
  if [ "$prev_sha" = "$sha" ]; then
    # Re-deploying the same SHA keeps the earlier rollback target.
    prev_sha="$(state_value previous_sha)"
    prev_tag="$(state_value previous_tag)"
  elif [ -z "$prev_tag" ]; then
    prev_tag="$(running_tag)"
    prev_sha="$prev_tag"
  fi

  say "deploying $sha (tag $tag)"
  compose "$tag" build || abort "$sha" "image build"
  compose "$tag" run --rm backup now "$label" || abort "$sha" "pre-deploy backup"
  rev_before="$(alembic_current "$tag")" || abort "$sha" "alembic current"
  compose "$tag" --profile migrate run --rm migrate || abort "$sha" "migrations"
  rev_after="$(alembic_current "$tag")" || abort "$sha" "alembic current after migrations"
  say "database revision $rev_before -> $rev_after"

  prev_rev="$rev_before"
  if [ "$(state_value current_sha)" = "$sha" ]; then
    prev_rev="$(state_value previous_rev)"
  fi
  write_state "$sha" "$tag" "$rev_after" "$prev_sha" "$prev_tag" "$prev_rev" "$label"

  if compose "$tag" up -d && smoke; then
    say "deployed $sha"
    log_line deploy "$sha" success
    alert "deployed ${sha:0:12} (database $rev_before -> $rev_after)"
    return 0
  fi

  say "smoke test FAILED for $sha: rolling back"
  log_line deploy "$sha" "failed: smoke test, rolling back"
  if do_rollback auto; then
    alert "deploy of ${sha:0:12} failed its smoke test; rolled back to ${prev_tag}"
  else
    alert "deploy of ${sha:0:12} failed its smoke test and could NOT be rolled back; see deploys.log"
  fi
  exit 1
}

# ---------------------------------------------------------------------------------- rollback

print_restore_steps() {
  local label="$1" prev_tag="$2"
  cat <<EOF
The deploy being undone ran a migration that is not reversible, so its downgrade would lose
data the previous version needs. Restore the pre-deploy backup instead (docs/operations.md,
"Backups and restore" > "Restoring for real" and "Deploy and rollback"):

  1. docker compose --env-file .env.prod -f compose.prod.yml stop api worker bot
  2. ls "\$BACKUP_HOST_DIR" | grep -- '-$label.dump.age'        # the pre-deploy backup
  3. scripts/restore-check.sh PATH/trainsync-…-$label.dump.age
  4. restore it into the live database (the pg_restore command in docs/operations.md)
  5. scripts/deploy.sh rollback --restored      # starts the previous images ($prev_tag)
EOF
}

# do_rollback MODE   MODE: manual | auto | restored
do_rollback() {
  local mode="$1" cur_sha cur_tag cur_rev prev_sha prev_tag prev_rev label head check status
  cur_sha="$(state_value current_sha)"
  cur_tag="$(state_value current_tag)"
  cur_rev="$(state_value current_rev)"
  prev_sha="$(state_value previous_sha)"
  prev_tag="$(state_value previous_tag)"
  prev_rev="$(state_value previous_rev)"
  label="$(state_value backup_label)"

  if [ -z "$prev_tag" ]; then
    say "rollback refused: no previous deploy recorded in $STATE_FILE"
    log_line rollback "${cur_sha:-unknown}" "refused: no previous deploy"
    return 1
  fi
  if ! docker image inspect "trainsync:$prev_tag" >/dev/null 2>&1; then
    say "rollback refused: image trainsync:$prev_tag is gone"
    say "rebuild it: git switch --detach $prev_sha && TRAINSYNC_TAG=$prev_tag scripts/mac-prod.sh build"
    log_line rollback "$cur_sha" "refused: image trainsync:$prev_tag missing"
    return 1
  fi

  if [ "$mode" != restored ] && [ "$cur_rev" != "$prev_rev" ]; then
    head="$(git -C "$ROOT" rev-parse HEAD)"
    if [ "$head" != "$cur_sha" ]; then
      say "rollback refused: the checkout is at $head, not the deployed $cur_sha;"
      say "the migration check reads its files: git switch --detach $cur_sha, then run it again"
      log_line rollback "$cur_sha" "refused: checkout is not the deployed sha"
      return 1
    fi
    set +e
    check="$("$PYTHON" "$ROOT/scripts/migration_reversibility.py" --versions "$MIGRATIONS_DIR" \
      "$prev_rev" "$cur_rev")"
    status=$?
    set -e
    printf '%s\n' "$check" | sed 's/^/  /'
    if [ "$status" -eq 1 ]; then
      say "rollback refused: a migration between $prev_rev and $cur_rev is not reversible"
      print_restore_steps "$label" "$prev_tag"
      log_line rollback "$cur_sha" "refused: non-reversible migration"
      return 1
    elif [ "$status" -ne 0 ]; then
      say "rollback refused: could not check the migrations between $prev_rev and $cur_rev"
      log_line rollback "$cur_sha" "refused: migration check failed"
      return 1
    fi
    say "downgrading the database $cur_rev -> $prev_rev (with the image of $cur_tag)"
    if ! compose "$cur_tag" --profile migrate run --rm migrate alembic downgrade "$prev_rev"; then
      say "rollback FAILED: alembic downgrade $prev_rev"
      log_line rollback "$cur_sha" "failed: downgrade"
      return 1
    fi
  fi

  say "starting the previous images ($prev_tag)"
  if ! compose "$prev_tag" up -d; then
    log_line rollback "$cur_sha" "failed: up"
    return 1
  fi
  # One step back only: the restored version has no recorded predecessor.
  write_state "$prev_sha" "$prev_tag" "$prev_rev" "" "" "" ""
  if smoke; then
    say "rolled back to $prev_tag"
    log_line rollback "$prev_sha" "success ($mode, from ${cur_tag})"
    return 0
  fi
  say "rolled back to $prev_tag, but its smoke test failed too"
  log_line rollback "$prev_sha" "failed: smoke test ($mode, from ${cur_tag})"
  return 1
}

cmd_rollback() {
  local mode=manual
  case "${1:-}" in
    "") ;;
    --restored) mode=restored ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  [ -f "$ENV_FILE" ] || {
    say "$ENV_FILE is missing"
    exit 1
  }
  lock
  local from
  from="$(state_value current_tag)"
  if do_rollback "$mode"; then
    alert "rolled back from ${from:-unknown} to $(state_value current_tag)"
  else
    alert "rollback from ${from:-unknown} failed or was refused; see deploys.log"
    exit 1
  fi
}

cmd_status() {
  if [ ! -f "$STATE_FILE" ]; then
    say "no deploy recorded ($STATE_FILE)"
    return 0
  fi
  cat "$STATE_FILE"
}

main() {
  local command="${1:-}"
  [ $# -gt 0 ] && shift
  case "$command" in
    deploy) cmd_deploy ;;
    rollback) cmd_rollback "$@" ;;
    status) cmd_status ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
