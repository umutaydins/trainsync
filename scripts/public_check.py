"""`make public-check URL=https://<host>.ts.net` (P7.3): the public surface, seen from outside.

Runs from anywhere with internet (a laptop on another network, or the scheduled GitHub Actions
workflow `.github/workflows/public-check.yml`) against the Funnel URL:

1. TLS: the URL must be https and the certificate must verify (a normal HTTPS request).
2. Every allowlisted route in deploy/gateway/routes.toml is forwarded (its probe is neither 404
   nor a 5xx); routes behind `when_env` are expected off, like in `make prod-check`.
3. Every blocked probe (`/metrics`, `/docs`, `/`, ...) is 404.
4. `/health/live` is 200 and carries the gateway's security headers.

    uv run python scripts/public_check.py --url https://mac.tail1234.ts.net
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_gateway import Gateway, load

TIMEOUT = httpx.Timeout(15.0)


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def check(self, ok: bool, message: str) -> None:
        (self.passed if ok else self.failed).append(message)


def _get(client: httpx.Client, path: str) -> httpx.Response | str:
    try:
        return client.get(path)
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"


def run(base_url: str, client: httpx.Client, gateway: Gateway) -> Report:
    report = Report()
    if not base_url.startswith("https://"):
        report.check(False, f"{base_url} is not an https URL")
        return report

    health = _get(client, "/health/live")
    if isinstance(health, str):
        report.check(False, f"TLS/connection to {base_url} failed: {health}")
        return report
    report.check(True, f"TLS certificate of {base_url} verifies")
    headers = health.headers
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
    if report.failed:
        total = len(report.passed) + len(report.failed)
        print(f"public-check: FAILED ({len(report.failed)} of {total} checks)")
        return 1
    print(f"public-check: OK ({len(report.passed)} checks against {base_url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
