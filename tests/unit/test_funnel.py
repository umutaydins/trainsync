"""P7.3: scripts/funnel.sh against a stub `tailscale` (see tests/support/shell.py)."""

from pathlib import Path

import pytest

from tests.support.shell import ROOT, Mac
from tests.support.shell import write as _write

FUNNEL = ROOT / "scripts" / "funnel.sh"
STATUS_JSON = """{
  "BackendState": "Running",
  "Self": {
    "HostName": "trainsync",
    "DNSName": "trainsync.tail1234.ts.net.",
    "OS": "macOS"
  },
  "Peer": {
    "nodekey:1": {
      "DNSName": "desktop.tail1234.ts.net."
    }
  }
}"""


@pytest.fixture
def mac(tmp_path: Path) -> Mac:
    machine = Mac(tmp_path)
    machine.home.mkdir()
    _write(machine.env_file, "PUBLIC_API_BASE_URL=https://trainsync.tail1234.ts.net\n")
    machine.stub(
        "tailscale",
        'case "$1" in\n'
        f"  status) cat <<'EOF'\n{STATUS_JSON}\nEOF\n ;;\n"
        '  funnel) [ "$2" = status ] && echo "https://trainsync.tail1234.ts.net (Funnel on)" ;;\n'
        "esac",
    )
    return machine


def _tailscale_calls(mac: Mac) -> list[str]:
    return [line for line in mac.call_lines() if line.startswith("tailscale funnel")]


def test_on_forwards_443_to_the_real_gateway(mac: Mac) -> None:
    result = mac.run(FUNNEL, "on")
    assert result.returncode == 0, result.stderr
    assert _tailscale_calls(mac) == [
        "tailscale funnel --bg --https=443 http://127.0.0.1:8080",
        "tailscale funnel status",
    ]


def test_on_all_adds_the_demo_on_8443(mac: Mac) -> None:
    result = mac.run(FUNNEL, "on", "all", DEMO_GATEWAY_PORT="9081")
    assert result.returncode == 0, result.stderr
    assert "tailscale funnel --bg --https=8443 http://127.0.0.1:9081" in _tailscale_calls(mac)


def test_gateway_port_comes_from_the_env_file(mac: Mac) -> None:
    _write(mac.env_file, "GATEWAY_PORT=18080\n")
    mac.run(FUNNEL, "on")
    assert _tailscale_calls(mac)[0] == "tailscale funnel --bg --https=443 http://127.0.0.1:18080"


def test_off_turns_both_ports_off_by_default(mac: Mac) -> None:
    result = mac.run(FUNNEL, "off")
    assert result.returncode == 0, result.stderr
    assert _tailscale_calls(mac)[:2] == [
        "tailscale funnel --https=443 off",
        "tailscale funnel --https=8443 off",
    ]


def test_status_prints_the_public_urls_and_strava_values(mac: Mac) -> None:
    result = mac.run(FUNNEL, "status")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "(Funnel on)" in out
    assert "PUBLIC_API_BASE_URL=https://trainsync.tail1234.ts.net\n" in out
    assert (
        "OAuth redirect URI              https://trainsync.tail1234.ts.net/auth/strava/callback"
        in out
    )
    assert (
        "webhook callback_url            https://trainsync.tail1234.ts.net/webhooks/strava" in out
    )
    assert "Authorization Callback Domain   trainsync.tail1234.ts.net\n" in out
    assert "make public-check URL=https://trainsync.tail1234.ts.net" in out
    assert "desktop" not in out
    assert "WARN" not in out


def test_status_warns_when_the_env_file_points_elsewhere(mac: Mac) -> None:
    _write(mac.env_file, "PUBLIC_API_BASE_URL=https://old.example.com/\n")
    out = mac.run(FUNNEL, "status").stdout
    assert "WARN: PUBLIC_API_BASE_URL in" in out
    assert "is https://old.example.com, not https://trainsync.tail1234.ts.net" in out


def test_status_warns_when_the_env_file_has_no_url(mac: Mac) -> None:
    mac.env_file.unlink()
    out = mac.run(FUNNEL, "status").stdout
    assert "WARN: PUBLIC_API_BASE_URL is not set" in out


def test_status_fails_without_a_magicdns_name(mac: Mac) -> None:
    mac.stub("tailscale", "echo '{}'")
    result = mac.run(FUNNEL, "status")
    assert result.returncode == 1
    assert "is Tailscale up?" in result.stderr


def test_unknown_target_is_refused(mac: Mac) -> None:
    result = mac.run(FUNNEL, "on", "staging")
    assert result.returncode == 1
    assert "unknown target 'staging'" in result.stderr
    assert _tailscale_calls(mac) == []
