"""P7.3: scripts/public_check.py against a respx-faked public gateway."""

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[3]
BASE = "https://mac.tail1234.ts.net"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Strict-Transport-Security": "max-age=31536000",
}


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


public_check = _load("public_check")


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """No real DNS in tests: the host resolves to one of Funnel's public relays."""
    addresses = ["185.40.234.75"]
    monkeypatch.setattr(public_check, "resolve_host", lambda host: addresses)
    return addresses


@pytest.fixture
def gateway() -> Iterator[respx.MockRouter]:
    """A healthy public gateway: allowlisted probes answer, everything else is 404."""
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.get("/health/live").respond(200, headers=SECURITY_HEADERS)
        router.get("/webhooks/strava").respond(403)
        router.get("/auth/strava/login").respond(302, headers={"Location": "https://strava"})
        router.get("/v1/sync/status").respond(401)
        router.route(name="fallback").respond(404)
        yield router


def _serve(gateway: respx.MockRouter, path: str) -> respx.Route:
    """A route for `path` matched before the 404 fallback (respx matches in order)."""
    fallback = gateway.routes.pop("fallback")
    route = gateway.get(path)
    gateway.routes.add(fallback, name="fallback")
    return route


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = public_check.main(list(args))
    return code, capsys.readouterr().out


def test_healthy_gateway_passes(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(capsys, "--url", BASE + "/")
    assert code == 0, out
    assert "TLS certificate of https://mac.tail1234.ts.net verifies" in out
    assert "auth: /auth/strava/login forwarded (302)" in out
    assert "blocked: /metrics is 404 (404)" in out
    assert "FAIL" not in out
    probed = {call.request.url.path for call in gateway.calls}
    assert {"/metrics", "/openapi.json", "/v1/sync/status", "/webhooks/strava"} <= probed


def test_redirects_are_not_followed(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(capsys, "--url", BASE)
    assert all(call.request.url.host == "mac.tail1234.ts.net" for call in gateway.calls)


def test_an_exposed_internal_path_fails(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    _serve(gateway, "/metrics").respond(200)
    code, out = _run(capsys, "--url", BASE)
    assert code == 1
    assert "FAIL  blocked: /metrics is 404 (200)" in out


@pytest.mark.parametrize("status", [404, 502])
def test_an_allowlisted_route_that_is_not_served_fails(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    gateway.get("/v1/sync/status").respond(status)
    code, out = _run(capsys, "--url", BASE)
    assert code == 1
    assert f"FAIL  api: /v1/sync/status forwarded ({status})" in out


def test_missing_security_headers_fail(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway.get("/health/live").respond(200, headers={"Server": "uvicorn"})
    code, out = _run(capsys, "--url", BASE)
    assert code == 1
    assert "FAIL  /health/live: 200, security headers" in out


def test_a_tls_failure_fails_fast(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway.get("/health/live").mock(
        side_effect=httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    )
    code, out = _run(capsys, "--url", BASE)
    assert code == 1
    assert "FAIL  TLS/connection to https://mac.tail1234.ts.net failed: ConnectError" in out
    assert len(gateway.calls) == 1


def test_a_transport_error_on_a_probe_fails(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    _serve(gateway, "/redoc").mock(side_effect=httpx.ReadTimeout("timed out"))
    code, out = _run(capsys, "--url", BASE)
    assert code == 1
    assert "FAIL  blocked: /redoc is 404 (ReadTimeout: timed out)" in out


def test_plain_http_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "--url", "http://mac.tail1234.ts.net")
    assert code == 1
    assert "is not an https URL" in out


def test_no_url_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PUBLIC_CHECK_URL", raising=False)
    assert public_check.main([]) == 2
    assert "make public-check URL=" in capsys.readouterr().err


def test_url_from_the_environment(
    gateway: respx.MockRouter,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PUBLIC_CHECK_URL", BASE)
    code, out = _run(capsys)
    assert code == 0, out


@pytest.mark.parametrize("address", ["100.101.102.103", "fd7a:115c:a1e0::1234"])
def test_a_tailnet_address_warns_loudly(
    gateway: respx.MockRouter,
    capsys: pytest.CaptureFixture[str],
    public_dns: list[str],
    address: str,
) -> None:
    public_dns[:] = [address]
    code, out = _run(capsys, "--url", BASE)
    assert code == 0  # the gateway itself is fine; only the proof is missing
    assert f"WARN  mac.tail1234.ts.net resolves to the tailnet ({address})" in out
    assert "NOT A PUBLIC CHECK" in out


def test_a_tailscale_user_header_warns_loudly(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    headers = {**SECURITY_HEADERS, "Tailscale-User-Login": "owner@example.com"}
    _serve(gateway, "/health/live").respond(200, headers=headers)
    code, out = _run(capsys, "--url", BASE)
    assert code == 0
    assert "Tailscale-User-Login (owner@example.com)" in out
    assert "NOT A PUBLIC CHECK" in out


def test_a_public_run_has_no_warning(
    gateway: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = _run(capsys, "--url", BASE)
    assert "WARN" not in out
    assert "NOT A PUBLIC CHECK" not in out


def test_tailnet_ranges() -> None:
    assert public_check.tailnet_addresses(
        ["100.64.0.1", "100.127.255.254", "100.128.0.1", "185.40.234.55", "fd7a:115c:a1e0::1", "x"]
    ) == ["100.64.0.1", "100.127.255.254", "fd7a:115c:a1e0::1"]
