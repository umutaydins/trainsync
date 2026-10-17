#!/usr/bin/env bash
# Load test against the compose stack: start it with 5,000 fake activities, connect the athlete,
# wait for the backfill, run locust headless, write CSV + markdown summary, tear down (always).
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000}
PROJECT=${COMPOSE_PROJECT_NAME:-trainsync-loadtest}
USERS=${LOADTEST_USERS:-50}
SPAWN_RATE=${LOADTEST_SPAWN_RATE:-10}
DURATION=${LOADTEST_DURATION:-2m}
# Optional: only some user classes, e.g. LOADTEST_CLASSES=WebhookSender
CLASSES=${LOADTEST_CLASSES:-}
NAME=${LOADTEST_NAME:-run}
OUT=loadtest/results
export FAKE_STRAVA_SEED_ACTIVITIES=${FAKE_STRAVA_SEED_ACTIVITIES:-5000}
export POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-15433} REDIS_HOST_PORT=${REDIS_HOST_PORT:-16380}
compose() { docker compose -p "$PROJECT" "$@"; }

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "loadtest: FAILED, recent logs:" >&2
    compose logs --tail=50 api worker fake-strava >&2 || true
  fi
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT
fail() { echo "loadtest: $*" >&2; exit 1; }

echo "loadtest: starting stack ($FAKE_STRAVA_SEED_ACTIVITIES fake activities)"
compose up -d --build --wait --wait-timeout 180

echo "loadtest: connecting the athlete"
authorize=$(curl -sS -o /dev/null -w '%{redirect_url}' "$API/auth/strava/login")
callback=$(curl -sS -o /dev/null -w '%{redirect_url}' "$authorize")
curl -fsS "$callback" >/dev/null || fail "oauth callback failed"

echo "loadtest: waiting for the backfill"
status_json=""
for _ in $(seq 1 120); do
  status_json=$(curl -fsS -H "X-API-Key: dev-key-1" "$API/v1/sync/status")
  case "$status_json" in *'"backfill":{'*'"status":"succeeded"'*) break ;; esac
  sleep 1
done
case "$status_json" in *'"status":"succeeded"'*) ;; *) fail "backfill did not finish: $status_json" ;; esac
owner=$(printf '%s' "$status_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["athletes"][0]["strava_athlete_id"])')
stored=$(compose exec -T postgres psql -U trainsync -d trainsync -tAc "select count(*) from activities")
echo "  athlete $owner, $stored activities stored"

mkdir -p "$OUT"
echo "loadtest: locust $USERS users ${CLASSES:-all classes}, spawn rate $SPAWN_RATE/s, $DURATION"
# shellcheck disable=SC2086  # CLASSES is a space-separated list of class names
LOADTEST_OWNER_ID=$owner uv run --group loadtest locust -f loadtest/locustfile.py --headless \
  --host "$API" --users "$USERS" --spawn-rate "$SPAWN_RATE" --run-time "$DURATION" \
  --csv "$OUT/$NAME" --only-summary $CLASSES

uv run python scripts/loadtest_summary.py "$OUT/${NAME}_stats.csv" | tee "$OUT/$NAME-summary.md"
echo "loadtest: OK ($OUT/${NAME}_stats.csv, $OUT/$NAME-summary.md)"
