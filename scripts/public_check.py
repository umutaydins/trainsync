"""`make public-check URL=https://<host>.ts.net` (P7.3): the public surface, seen from outside.

Runs from anywhere with internet (a laptop on another network, or the scheduled GitHub Actions
workflow `.github/workflows/public-check.yml`) against the Funnel URL:

1. TLS: the URL must be https and the certificate must verify (a normal HTTPS request).
2. Every allowlisted route in deploy/gateway/routes.toml is forwarded (its probe is neither 404
   nor a 5xx); routes behind `when_env` are expected off, like in `make prod-check`.
3. Every blocked probe (`/metrics`, `/docs`, `/`, ...) is 404.
4. `/health/live` is 200 and carries the gateway's security headers.

A run that reaches the Mac through the tailnet proves nothing about the public internet: when
the host resolves into Tailscale's address range (100.64.0.0/10, fd7a:115c:a1e0::/48, i.e.
MagicDNS on a tailnet device) or a response carries `Tailscale-User-Login` (only tailnet
traffic gets it), the checks still run but the result says loudly that public reachability was
not shown. Run it from a device outside the tailnet, or let the scheduled workflow do it.

    uv run python scripts/public_check.py --url https://mac.tail1234.ts.net
"""

import argparse
import ipaddress
import os
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_gateway import Gateway, load

TIMEOUT = httpx.Timeout(15.0)
TAILNET_RANGES = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)
TAILNET_HEADER = "tailscale-user-login"


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def check(self, ok: bool, message: str) -> None:
        (self.passed if ok else self.failed).append(message)


def resolve_host(host: str) -> list[str]:
    """Every address `host` resolves to here; empty when it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return []
    return sorted({str(info[4][0]) for info in infos})


def tailnet_addresses(addresses: list[str]) -> list[str]:
    tailnet = []
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            continue
        if any(ip in network for network in TAILNET_RANGES):
            tailnet.append(address)
    return tailnet


def _get(client: httpx.Client, path: str) -> httpx.Response | str:
    try:
        return client.get(path)
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"


def run(
    base_url: str,
    client: httpx.Client,
    gateway: Gateway,
    resolve: Callable[[str], list[str]] | None = None,
) -> Report:
    report = Report()
    if not base_url.startswith("https://"):
        report.check(False, f"{base_url} is not an https URL")
        return report
    host = urlsplit(base_url).hostname or ""
    inside = tailnet_addresses((resolve or resolve_host)(host))
    if inside:
        report.warnings.append(
            f"{host} resolves to the tailnet ({', '.join(inside)}): this run went through "
            "Tailscale, not through Funnel's public relays"
        )

    health = _get(client, "/health/live")
    if isinstance(health, str):
        report.check(False, f"TLS/connection to {base_url} failed: {health}")
        return report
    report.check(True, f"TLS certificate of {base_url} verifies")
    headers = health.headers
    if TAILNET_HEADER in headers:
        report.warnings.append(
            f"the response carries Tailscale-User-Login ({headers[TAILNET_HEADER]}): "
            "it came from inside the tailnet"
        )
    report.check(
        health.status_code == 200
        and headers.get("x-content-type-options") == "nosniff"
        and "strict-transport-security" in headers
        and "server" not in headers,
        f"/health/live: {health.status_code}, security headers from the gateway",
    )

    for route in gateway.routes:
        if route.when_env:
            continue  # off unless enabled; its probe is in the blocked list
        response = _get(client, route.probe)
        status = response if isinstance(response, str) else response.status_code
        forwarded = isinstance(status, int) and status != 404 and status < 500
        report.check(forwarded, f"{route.name}: {route.probe} forwarded ({status})")

    for path in gateway.blocked_probes:
        response = _get(client, path)
        status = response if isinstance(response, str) else response.status_code
        report.check(status == 404, f"blocked: {path} is 404 ({status})")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("PUBLIC_CHECK_URL", ""))
    args = parser.parse_args(argv)
    base_url = args.url.strip().rstrip("/")
    if not base_url:
        print("public-check: no URL (make public-check URL=https://<host>.ts.net)", file=sys.stderr)
        return 2
    with httpx.Client(base_url=base_url, timeout=TIMEOUT, follow_redirects=False) as client:
        report = run(base_url, client, load())
    for message in report.passed:
        print(f"  ok    {message}")
    for message in report.failed:
        print(f"  FAIL  {message}")
    for message in report.warnings:
        print(f"  WARN  {message}")
    if report.warnings:
        print(
            "public-check: WARNING: NOT A PUBLIC CHECK. These results do not prove that the "
            "internet can reach the URL. Run it from a device outside the tailnet (phone on "
            "mobile data, `gh workflow run public-check.yml`) or an external probe."
        )
    if report.failed:
        total = len(report.passed) + len(report.failed)
        print(f"public-check: FAILED ({len(report.failed)} of {total} checks)")
        return 1
    print(f"public-check: OK ({len(report.passed)} checks against {base_url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
