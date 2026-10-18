#!/usr/bin/env bash
# Bring the compose stack up, prove it is healthy and that the OAuth flow stores an athlete with
# encrypted tokens, then tear it down again (always, even on failure).
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000}
WEB=${WEB:-http://localhost:3000}
PROJECT=${COMPOSE_PROJECT_NAME:-trainsync-smoke}
# The smoke test talks to postgres/redis through `docker compose exec`, so their host ports only
# need to be free, not standard.
export POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-15432} REDIS_HOST_PORT=${REDIS_HOST_PORT:-16379}
compose() { docker compose -p "$PROJECT" "$@"; }

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "smoke: FAILED, recent logs:" >&2
    compose logs --tail=50 api worker migrate fake-strava web >&2 || true
  fi
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

fail() { echo "smoke: $*" >&2; exit 1; }
sql() { compose exec -T postgres psql -U trainsync -d trainsync -tAc "$1"; }

echo "smoke: starting stack"
compose up -d --build --wait --wait-timeout 180

echo "smoke: readiness"
ready=$(curl -fsS "$API/health/ready") || fail "/health/ready not 200"
echo "  $ready"

echo "smoke: oauth flow"
authorize=$(curl -sS -o /dev/null -w '%{redirect_url}' "$API/auth/strava/login")
case "$authorize" in http://localhost:8001/oauth/authorize\?*) ;; *) fail "unexpected login redirect: $authorize";; esac
callback=$(curl -sS -o /dev/null -w '%{redirect_url}' "$authorize")
case "$callback" in "$API"/auth/strava/callback\?*) ;; *) fail "unexpected authorize redirect: $callback";; esac
body=$(curl -fsS "$callback") || fail "callback failed"
echo "  $body"
case "$body" in *'"backfill":"queued"'*) ;; *) fail "callback did not queue a backfill";; esac

echo "smoke: database"
athletes=$(sql "select count(*) from athletes where active")
[ "$athletes" = "1" ] || fail "expected 1 active athlete, got $athletes"
# Fernet tokens are url-safe base64 starting with version byte 0x80 -> 'gAAAAA'.
encrypted=$(sql "select count(*) from oauth_tokens where convert_from(access_token_enc, 'UTF8') like 'gAAAAA%' and convert_from(refresh_token_enc, 'UTF8') like 'gAAAAA%'")
[ "$encrypted" = "1" ] || fail "tokens are not stored as Fernet ciphertext"

echo "smoke: web dashboard"
web_dir=$(mktemp -d)
jar="$web_dir/cookies"
code=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "$WEB/")
case "$code" in "307 $WEB/login"*) ;; *) fail "web / without a session: $code";; esac
code=$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/api/ts/v1/sync/status")
[ "$code" = "401" ] || fail "BFF without a session: $code"
code=$(curl -sS -o /dev/null -w '%{http_code}' -d password=wrong "$WEB/api/auth/login")
[ "$code" = "401" ] || fail "wrong password: $code"
code=$(curl -sS -o /dev/null -w '%{http_code}' -c "$jar" -d password=dev-only-dashboard-password "$WEB/api/auth/login")
[ "$code" = "303" ] || fail "right password: $code"
summary=$(curl -fsS -b "$jar" "$WEB/api/ts/v1/stats/summary") || fail "BFF summary failed"
case "$summary" in *'"totals"'*) ;; *) fail "unexpected BFF summary: $summary";; esac
case "$summary" in *dev-key-1*) fail "BFF response contains the API key";; esac
code=$(curl -sS -o /dev/null -w '%{http_code}' -b "$jar" -X POST "$WEB/api/ts/v1/sync/status")
[ "$code" = "405" ] || fail "BFF POST: $code"
rm -rf "$web_dir"
echo "  login gate, BFF and key isolation OK"

echo "smoke: OK"
