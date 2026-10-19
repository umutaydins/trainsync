#!/usr/bin/env bash
# Public HTTPS for the gateways through Tailscale Funnel (P7.3).
#
#   scripts/funnel.sh on [real|demo|all]    real (default): https://<host>/     -> 127.0.0.1:8080
#                                           demo:           https://<host>:8443/ -> 127.0.0.1:8081
#   scripts/funnel.sh off [real|demo|all]   all by default
#   scripts/funnel.sh status                Funnel config, the public URLs and the Strava values
#
# Funnel terminates TLS on the Tailscale node (a Let's Encrypt certificate for <host>.ts.net) and
# forwards plain HTTP to the gateway, which serves only the allowlisted routes (ADR 0022).
# Funnel allows only ports 443, 8443 and 10000. Overridable: GATEWAY_PORT (8080),
# DEMO_GATEWAY_PORT (8081), TRAINSYNC_ENV_FILE (<repo>/.env.prod).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${TRAINSYNC_ENV_FILE:-$ROOT/.env.prod}"

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
  echo "funnel: $*" >&2
  exit 1
}

env_value() {
  local line
  [ -f "$ENV_FILE" ] || return 0
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  printf '%s' "$line"
}

tailscale_cmd() {
  if command -v tailscale >/dev/null 2>&1; then
    echo tailscale
  elif [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]; then
    echo /Applications/Tailscale.app/Contents/MacOS/Tailscale
  else
    die "tailscale not found: install the Tailscale app from tailscale.com/download/mac"
  fi
}

TS="$(tailscale_cmd)"
REAL_PORT="${GATEWAY_PORT:-$(env_value GATEWAY_PORT)}"
REAL_PORT="${REAL_PORT:-8080}"
DEMO_PORT="${DEMO_GATEWAY_PORT:-$(env_value DEMO_GATEWAY_PORT)}"
DEMO_PORT="${DEMO_PORT:-8081}"

# This node's MagicDNS name (the "Self" entry of `tailscale status --json`), without the final dot.
public_host() {
  "$TS" status --json 2>/dev/null | awk '
    /"Self"[[:space:]]*:/ { self = 1 }
    self && /"DNSName"[[:space:]]*:/ {
      sub(/.*"DNSName"[[:space:]]*:[[:space:]]*"/, ""); sub(/\.?".*/, ""); print; exit
    }'
}

targets() {
  case "${1:-}" in
    real) echo real ;;
    demo) echo demo ;;
    all) echo "real demo" ;;
    *) die "unknown target '${1:-}': real, demo or all" ;;
  esac
}

funnel_on() {
  local target list
  list="$(targets "${1:-real}")"
  for target in $list; do
    case "$target" in
      real) "$TS" funnel --bg --https=443 "http://127.0.0.1:$REAL_PORT" ;;
      demo) "$TS" funnel --bg --https=8443 "http://127.0.0.1:$DEMO_PORT" ;;
    esac
  done
  funnel_status
}

funnel_off() {
  local target list
  list="$(targets "${1:-all}")"
  for target in $list; do
    case "$target" in
      real) "$TS" funnel --https=443 off || true ;;
      demo) "$TS" funnel --https=8443 off || true ;;
    esac
  done
  "$TS" funnel status || true
}

funnel_status() {
  local host base configured
  "$TS" funnel status || true
  host="$(public_host)"
  [ -n "$host" ] || die "no MagicDNS name: is Tailscale up? (tailscale status)"
  base="https://$host"
  configured="$(env_value PUBLIC_API_BASE_URL)"
  configured="${configured%/}"
  cat <<EOF

Public URLs
  real backend              $base/          (-> 127.0.0.1:$REAL_PORT)
  demo backend              $base:8443/     (-> 127.0.0.1:$DEMO_PORT)
.env.prod
  PUBLIC_API_BASE_URL=$base
Strava API application (docs/strava-setup.md)
  Authorization Callback Domain   $host
  OAuth redirect URI              $base/auth/strava/callback
  webhook callback_url            $base/webhooks/strava
Vercel (web/, P7.6): the BFF calls the backend server-side, so no CORS is involved
  TRAINSYNC_API_URL=$base
Check from outside
  make public-check URL=$base
EOF
  if [ -z "$configured" ]; then
    echo "WARN: PUBLIC_API_BASE_URL is not set in $ENV_FILE; set it to $base"
  elif [ "$configured" != "$base" ]; then
    echo "WARN: PUBLIC_API_BASE_URL in $ENV_FILE is $configured, not $base"
  fi
}

main() {
  local command="${1:-}"
  [ $# -gt 0 ] && shift
  case "$command" in
    on) funnel_on "$@" ;;
    off) funnel_off "$@" ;;
    status) funnel_status ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
