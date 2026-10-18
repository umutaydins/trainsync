#!/usr/bin/env bash
# Run by the LaunchAgent com.trainsync.stack at login (P7.2): wait for Docker Desktop, then start
# the production stack. Output goes to ~/Library/Logs/trainsync/stack.log (see the plist).
#   DOCKER_WAIT_SECONDS  how long to wait for Docker (default 600)
#   DOCKER_POLL_SECONDS  pause between checks (default 5)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WAIT="${DOCKER_WAIT_SECONDS:-600}"
POLL="${DOCKER_POLL_SECONDS:-5}"

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S%z') start-stack: $*"; }

log "waiting up to ${WAIT}s for Docker"
# Docker Desktop normally starts itself at login; opening it again is harmless if it already is.
open -a Docker >/dev/null 2>&1 || true
waited=0
until docker info >/dev/null 2>&1; do
  if [ "$waited" -ge "$WAIT" ]; then
    log "Docker did not come up within ${WAIT}s; giving up (run: scripts/mac-prod.sh up)"
    exit 1
  fi
  sleep "$POLL"
  waited=$((waited + POLL))
done
log "Docker is up after ${waited}s"

if "$ROOT/scripts/mac-prod.sh" up; then
  log "stack started"
else
  status=$?
  log "scripts/mac-prod.sh up failed with exit $status"
  exit "$status"
fi
