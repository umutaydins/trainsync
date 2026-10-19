"""Render deploy/gateway/Caddyfile from deploy/gateway/routes.toml (P7.1).

    uv run python scripts/render_gateway.py           # write the Caddyfile
    uv run python scripts/render_gateway.py --check   # exit 1 if the committed one is stale

`is_routed` is the same allowlist in Python; the tests and `make prod-check` use it.
"""

import argparse
import fnmatch
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "deploy" / "gateway" / "routes.toml"
CADDYFILE = ROOT / "deploy" / "gateway" / "Caddyfile"
UPSTREAM = "api:8000"
# The webhook path with a query string; the access log keeps only the path ($1).
WEBHOOK_QUERY_RE = "^(/webhooks/strava[^?]*)[?].*$"


@dataclass(frozen=True)
class Route:
    name: str
    paths: list[str]
    max_body: str
    probe: str
    rate_limit: str | None = None
    when_env: str | None = None

    def matches(self, path: str) -> bool:
        # Caddy's `path` matcher: exact, or a `*` wildcard (fnmatch's `*` also crosses `/`, as
        # Caddy's does at the end of a pattern).
        return any(fnmatch.fnmatchcase(path, pattern) for pattern in self.paths)


@dataclass(frozen=True)
class Gateway:
    routes: list[Route]
    blocked_probes: list[str] = field(default_factory=list)


def load(path: Path = ROUTES) -> Gateway:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    routes = [Route(**route) for route in data["route"]]
    return Gateway(routes, list(data.get("blocked", {}).get("probes", [])))


def is_routed(path: str, env: dict[str, str] | None = None, gateway: Gateway | None = None) -> bool:
    env = env or {}
    gateway = gateway or load()
    for route in gateway.routes:
        if route.when_env and env.get(route.when_env) != "true":
            continue
        if route.matches(path):
            return True
    return False


def _route_block(route: Route) -> list[str]:
    matcher = f"@{route.name}"
    lines = [f"\t{matcher} {{", f"\t\tpath {' '.join(route.paths)}"]
    if route.when_env:
        # Substituted when Caddy parses the file: routed only if the variable is "true".
        lines.append(f'\t\texpression "{{${route.when_env}:false}}" == "true"')
    lines.append("\t}")
    lines.append(f"\thandle {matcher} {{")
    if route.rate_limit:
        events, window = route.rate_limit.split("/")
        lines += [
            "\t\trate_limit {",
            f"\t\t\tzone {route.name} {{",
            "\t\t\t\tkey {client_ip}",
            f"\t\t\t\tevents {events}",
            f"\t\t\t\twindow {window}",
            "\t\t\t}",
            "\t\t}",
        ]
    lines += [
        "\t\trequest_body {",
        f"\t\t\tmax_size {route.max_body}",
        "\t\t}",
        f"\t\treverse_proxy {UPSTREAM}",
        "\t}",
    ]
    return lines


def _log_filter(indent: str) -> list[str]:
    """Strava's subscription handshake puts hub.verify_token (a secret) in the query string of
    /webhooks/strava: log that path without any query. The API key header never reaches a log
    either (Caddy redacts only Cookie and Authorization by itself)."""
    return [
        f"{indent}format filter {{",
        f"{indent}\twrap json",
        f"{indent}\trequest>uri regexp {WEBHOOK_QUERY_RE} $1",
        f"{indent}\trequest>headers>X-Api-Key delete",
        f"{indent}}}",
    ]


def render(gateway: Gateway | None = None) -> str:
    gateway = gateway or load()
    lines = [
        "# GENERATED from routes.toml by scripts/render_gateway.py; do not edit by hand.",
        "{",
        "\tadmin off",
        "\tauto_https off",
        "\torder rate_limit before reverse_proxy",
        "\tservers {",
        # Tailscale Funnel (or another TLS terminator) in front: trust its X-Forwarded-For so
        # the rate limit keys on the real client.
        "\t\ttrusted_proxies static private_ranges",
        "\t\tclient_ip_headers X-Forwarded-For",
        "\t}",
        # Error logs (e.g. a 502 while the api restarts) carry the request too.
        "\tlog default {",
        "\t\toutput stdout",
        *_log_filter("\t\t"),
        "\t}",
        "}",
        "",
        ":8080 {",
        "\theader {",
        "\t\t-Server",
        "\t\tX-Content-Type-Options nosniff",
        "\t\tX-Frame-Options DENY",
        "\t\tReferrer-Policy no-referrer",
        '\t\tStrict-Transport-Security "max-age=31536000"',
        "\t\tContent-Security-Policy \"frame-ancestors 'none'\"",
        "\t}",
        "\tlog {",
        "\t\toutput stdout",
        *_log_filter("\t\t"),
        "\t}",
        "",
    ]
    for route in gateway.routes:
        lines += _route_block(route)
        lines.append("")
    lines += ["\thandle {", "\t\trespond 404", "\t}", "}", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the Caddyfile is stale")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        if CADDYFILE.read_text(encoding="utf-8") != rendered:
            print(
                "Caddyfile is stale: run uv run python scripts/render_gateway.py", file=sys.stderr
            )
            return 1
        return 0
    CADDYFILE.write_text(rendered, encoding="utf-8")
    print(f"wrote {CADDYFILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
