#!/usr/bin/env bash
# Start the compose stack (with `web`), run the Playwright e2e suite in web/e2e against it, and tear
# the stack down again (always, even on failure). Screenshots land in docs/img/.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=${COMPOSE_PROJECT_NAME:-trainsync-e2e}
export POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-15432} REDIS_HOST_PORT=${REDIS_HOST_PORT:-16379}
# The e2e logs manually created foods only: no Open Food Facts calls from the stack.
export OPENFOODFACTS_ENABLED=false
compose() { docker compose -p "$PROJECT" "$@"; }

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "e2e: FAILED, recent logs:" >&2
    compose logs --tail=50 api worker web fake-strava >&2 || true
  fi
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

echo "e2e: installing web dependencies and the Playwright browser"
(cd web && pnpm install --frozen-lockfile && pnpm exec playwright install ${PLAYWRIGHT_INSTALL_ARGS:-} chromium)

echo "e2e: starting stack"
compose up -d --build --wait --wait-timeout 300

echo "e2e: running Playwright"
(cd web && pnpm exec playwright test)
echo "e2e: OK"
