#!/usr/bin/env bash
# Control the production stack on the Mac (P7.2): one entry point for compose.prod.yml.
#
#   scripts/mac-prod.sh up                 migrations (one-shot), then the stack in the background
#   scripts/mac-prod.sh build              build the images for the current tag
#   scripts/mac-prod.sh down               stop the stack (volumes are kept)
#   scripts/mac-prod.sh status             containers and their health
#   scripts/mac-prod.sh logs [service]     follow logs (all services, or one)
#   scripts/mac-prod.sh restart [service]  restart the stack, or one service
#   scripts/mac-prod.sh doctor             check the Mac is fit to serve; prints a fix per failure
#   scripts/mac-prod.sh install-agent      install + load the LaunchAgent (start at login)
#   scripts/mac-prod.sh uninstall-agent    unload + remove the LaunchAgent
#   scripts/mac-prod.sh compose ARGS...    any docker compose command on the prod stack
#   scripts/mac-prod.sh tag                print the image tag the commands above use
#
# Every external command (docker, pmset, tailscale, df, curl, launchctl, fdesetup, git, ...) is
# looked up on PATH, so tests run this script against stub commands. Overridable settings:
#   TRAINSYNC_ENV_FILE  default <repo>/.env.prod
#   TRAINSYNC_TAG       image tag; default: the value in the env file, else the tag the last
#                       deploy/rollback started (TRAINSYNC_STATE_DIR/deploy-state, P7.5), else
#                       the tag of the running api container (as deploy.sh), else the git SHA
#   BACKUP_DIR          default the iCloud Drive folder trainsync-backups (P7.4)
#   BACKUP_MAX_AGE_HOURS (36), MIN_FREE_GB (10), GATEWAY_PORT (8080)
#   LAUNCH_AGENTS_DIR   default ~/Library/LaunchAgents;  TRAINSYNC_LOG_DIR default ~/Library/Logs/trainsync
#   DOCKER_SETTINGS     Docker Desktop settings file (AutoStart)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${TRAINSYNC_ENV_FILE:-$ROOT/.env.prod}"
COMPOSE_FILE="$ROOT/compose.prod.yml"
AGENT_LABEL="com.trainsync.stack"
AGENT_TEMPLATE="$ROOT/deploy/macos/$AGENT_LABEL.plist"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
LOG_DIR="${TRAINSYNC_LOG_DIR:-$HOME/Library/Logs/trainsync}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/trainsync-backups}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-36}"
MIN_FREE_GB="${MIN_FREE_GB:-10}"
DEPLOY_STATE="${TRAINSYNC_STATE_DIR:-$HOME/Library/Application Support/trainsync}/deploy-state"
DOCKER_SETTINGS="${DOCKER_SETTINGS:-$HOME/Library/Group Containers/group.com.docker/settings-store.json}"

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
  echo "mac-prod: $*" >&2
  exit 1
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

resolve_tag() {
  if [ -n "${TRAINSYNC_TAG:-}" ]; then
    printf '%s' "$TRAINSYNC_TAG"
    return
  fi
  local tag
  tag="$(env_value TRAINSYNC_TAG)"
  if [ -z "$tag" ] && [ -f "$DEPLOY_STATE" ]; then
    # What `make deploy` / `make rollback` last started (P7.5): a reboot after a rollback brings
    # back the rolled-back-to version, not the checked-out commit.
    tag="$(grep -E '^current_tag=' "$DEPLOY_STATE" | tail -n 1 | cut -d= -f2- || true)"
  fi
  if [ -z "$tag" ] && [ -f "$ENV_FILE" ]; then
    # No deploy recorded: whatever is running now (deploy.sh's running_tag). The compose file
    # needs some tag to parse, so the lookup itself runs with a placeholder.
    local image
    image="$(TRAINSYNC_TAG=unknown docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
      ps --format '{{.Image}}' api 2>/dev/null | head -n 1 || true)"
    case "$image" in
      trainsync:*) tag="${image#trainsync:}" ;;
    esac
  fi
  if [ -z "$tag" ]; then
    tag="$(git -C "$ROOT" rev-parse --short=12 HEAD)" || die "no TRAINSYNC_TAG and no git SHA"
  fi
  printf '%s' "$tag"
}

compose() {
  [ -f "$ENV_FILE" ] || die "$ENV_FILE is missing: cp .env.prod.example .env.prod, fill it in, chmod 600 .env.prod"
  TRAINSYNC_TAG="$(resolve_tag)"
  export TRAINSYNC_TAG
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

cmd_up() {
  echo "mac-prod: up (TRAINSYNC_TAG=$(resolve_tag))"
  compose --profile migrate run --rm migrate
  compose up -d
}

# ------------------------------------------------------------------------------------- doctor

FAILURES=0
WARNINGS=0

ok() { printf '  ok    %s\n' "$1"; }
bad() {
  printf '  FAIL  %s\n        fix: %s\n' "$1" "$2"
  FAILURES=$((FAILURES + 1))
}
warn() {
  printf '  WARN  %s\n        fix: %s\n' "$1" "$2"
  WARNINGS=$((WARNINGS + 1))
}

tailscale_cmd() {
  if command -v tailscale >/dev/null 2>&1; then
    echo tailscale
  elif [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]; then
    echo /Applications/Tailscale.app/Contents/MacOS/Tailscale
  fi
}

check_env_file() {
  if [ ! -f "$ENV_FILE" ]; then
    bad "env file $ENV_FILE is missing" "cp .env.prod.example .env.prod && chmod 600 .env.prod  # then fill in every value"
    return
  fi
  if [ -n "$(find "$ENV_FILE" \( -perm -004 -o -perm -040 -o -perm -002 -o -perm -020 \) -print)" ]; then
    bad "env file $ENV_FILE is readable by others" "chmod 600 $ENV_FILE"
  else
    ok "env file present, private"
  fi
}

check_docker_running() {
  if docker info >/dev/null 2>&1; then
    ok "Docker is running"
  else
    bad "Docker is not running" "open -a Docker"
  fi
}

check_docker_autostart() {
  local settings="$DOCKER_SETTINGS"
  [ -f "$settings" ] || settings="$(dirname "$DOCKER_SETTINGS")/settings.json"
  if [ -f "$settings" ] && grep -Eq '"[Aa]uto[Ss]tart"[[:space:]]*:[[:space:]]*true' "$settings"; then
    ok "Docker Desktop starts at login"
  else
    bad "Docker Desktop does not start at login" \
      "Docker Desktop > Settings > General > enable 'Start Docker Desktop when you sign in'"
  fi
}

# `pmset -g custom` prints "Battery Power:" and "AC Power:" sections; check the AC one.
pmset_ac_value() {
  pmset -g custom 2>/dev/null | awk -v key="$1" '
    /^[A-Za-z].*Power:/ { ac = ($0 ~ /^AC Power:/) }
    ac && $1 == key { print $2; exit }'
}

check_sleep() {
  local sleep_value disksleep_value
  sleep_value="$(pmset_ac_value sleep)"
  disksleep_value="$(pmset_ac_value disksleep)"
  if [ "$sleep_value" = "0" ] && [ "$disksleep_value" = "0" ]; then
    ok "no system or disk sleep on power"
  else
    bad "sleeps on power (sleep=${sleep_value:-?}, disksleep=${disksleep_value:-?})" \
      "sudo pmset -c sleep 0 disksleep 0"
  fi
}

check_disk() {
  local free_kb
  free_kb="$(df -Pk "$HOME" | awk 'NR == 2 { print $4 }')"
  if [ -z "$free_kb" ]; then
    bad "could not read free disk space" "df -h \"$HOME\""
  elif [ "$free_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
    bad "only $((free_kb / 1024 / 1024)) GB free (minimum $MIN_FREE_GB GB)" \
      "docker system prune  # and empty ~/Downloads, Trash"
  else
    ok "$((free_kb / 1024 / 1024)) GB free"
  fi
}

check_tailscale() {
  local ts
  ts="$(tailscale_cmd)"
  if [ -z "$ts" ]; then
    bad "Tailscale is not installed" "install the Tailscale app from tailscale.com/download/mac"
    return 1
  fi
  if "$ts" status --json 2>/dev/null | grep -Eq '"BackendState"[[:space:]]*:[[:space:]]*"Running"'; then
    ok "Tailscale is up"
  else
    bad "Tailscale is not connected" "open -a Tailscale  # then log in; or: tailscale up"
    return 1
  fi
}

check_funnel() {
  local ts port status
  ts="$(tailscale_cmd)"
  port="${GATEWAY_PORT:-$(env_value GATEWAY_PORT)}"
  port="${port:-8080}"
  status="$("$ts" funnel status 2>/dev/null || true)"
  if printf '%s' "$status" | grep -q '(Funnel on)' \
    && printf '%s' "$status" | grep -q "127.0.0.1:$port"; then
    ok "Funnel forwards to the gateway on 127.0.0.1:$port"
  else
    bad "no Funnel to the gateway on 127.0.0.1:$port" "scripts/funnel.sh on"
  fi
}

check_stack() {
  local port
  port="${GATEWAY_PORT:-$(env_value GATEWAY_PORT)}"
  port="${port:-8080}"
  if curl -fsS --max-time 5 "http://127.0.0.1:$port/health/ready" >/dev/null 2>&1; then
    ok "stack answers on http://127.0.0.1:$port/health/ready"
  else
    bad "stack does not answer on http://127.0.0.1:$port/health/ready" \
      "scripts/mac-prod.sh up  # then: scripts/mac-prod.sh status"
  fi
}

check_agent() {
  if [ ! -f "$LAUNCH_AGENTS_DIR/$AGENT_LABEL.plist" ]; then
    bad "LaunchAgent $AGENT_LABEL is not installed" "scripts/mac-prod.sh install-agent"
  elif ! launchctl print "gui/$(id -u)/$AGENT_LABEL" >/dev/null 2>&1; then
    bad "LaunchAgent $AGENT_LABEL is installed but not loaded" "scripts/mac-prod.sh install-agent"
  else
    ok "LaunchAgent $AGENT_LABEL is loaded"
  fi
}

# The LaunchAgent runs only once a user is logged in. FileVault keeps a rebooted Mac at the unlock
# screen until someone types the password (planned restarts can skip it with `fdesetup
# authrestart`); without FileVault, automatic login is what brings the session back.
check_login_after_reboot() {
  if fdesetup status 2>/dev/null | grep -q "FileVault is On"; then
    warn "FileVault is on: after an unplanned reboot the Mac waits at the unlock screen" \
      "for planned restarts use: sudo fdesetup authrestart  # see docs/operations.md, Reboot"
  elif [ -n "$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null)" ]; then
    ok "automatic login is on: the session (and the LaunchAgent) comes back after a reboot"
  else
    warn "automatic login is off: after a reboot nothing starts until you log in" \
      "System Settings > Users & Groups > Automatically log in as: <you>"
  fi
}

check_backup() {
  local newest
  newest="$(find "$BACKUP_DIR" -maxdepth 1 -name 'trainsync-*.dump.age' 2>/dev/null | sort | tail -n 1 || true)"
  if [ -z "$newest" ]; then
    warn "no backup in $BACKUP_DIR" "set up nightly backups (P7.4, docs/operations.md)"
  elif [ -z "$(find "$newest" -mmin "-$((BACKUP_MAX_AGE_HOURS * 60))" 2>/dev/null)" ]; then
    warn "newest backup $(basename "$newest") is older than ${BACKUP_MAX_AGE_HOURS} h" \
      "check the backup job logs in $LOG_DIR"
  else
    ok "last backup $(basename "$newest")"
  fi
}

cmd_doctor() {
  echo "mac-prod doctor"
  check_env_file
  check_docker_running
  check_docker_autostart
  check_sleep
  check_disk
  if check_tailscale; then
    check_funnel
  fi
  check_stack
  check_agent
  check_login_after_reboot
  check_backup
  if [ "$FAILURES" -gt 0 ]; then
    echo "doctor: $FAILURES failed, $WARNINGS warnings"
    return 1
  fi
  echo "doctor: OK ($WARNINGS warnings)"
}

# ------------------------------------------------------------------------------- LaunchAgent

cmd_install_agent() {
  local target="$LAUNCH_AGENTS_DIR/$AGENT_LABEL.plist" domain
  domain="gui/$(id -u)"
  mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
  # launchd does not expand ~ or variables: render absolute paths into the installed copy.
  sed -e "s|__ROOT__|$ROOT|g" -e "s|__LOG_DIR__|$LOG_DIR|g" "$AGENT_TEMPLATE" >"$target"
  launchctl bootout "$domain/$AGENT_LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "$domain" "$target"
  echo "installed $target (logs: $LOG_DIR/stack.log)"
}

cmd_uninstall_agent() {
  local target="$LAUNCH_AGENTS_DIR/$AGENT_LABEL.plist"
  launchctl bootout "gui/$(id -u)/$AGENT_LABEL" >/dev/null 2>&1 || true
  rm -f "$target"
  echo "removed $target (the running stack is untouched: scripts/mac-prod.sh down)"
}

main() {
  local command="${1:-}"
  [ $# -gt 0 ] && shift
  case "$command" in
    up) cmd_up ;;
    build) compose build ;;
    down) compose down ;;
    status) compose ps ;;
    logs) compose logs -f --tail=200 "$@" ;;
    restart) compose restart "$@" ;;
    doctor) cmd_doctor ;;
    install-agent) cmd_install_agent ;;
    uninstall-agent) cmd_uninstall_agent ;;
    compose) compose "$@" ;;
    tag) resolve_tag && echo ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
