"""P7.1: the public-route allowlist (deploy/gateway/routes.toml) and its rendered Caddyfile."""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _render_module() -> ModuleType:
    path = ROOT / "scripts" / "render_gateway.py"
    spec = importlib.util.spec_from_file_location("render_gateway", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_gateway"] = module
    spec.loader.exec_module(module)
    return module


gateway = _render_module()


def test_committed_caddyfile_is_rendered_from_routes() -> None:
    assert gateway.CADDYFILE.read_text(encoding="utf-8") == gateway.render(), (
        "run: uv run python scripts/render_gateway.py"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/webhooks/strava",
        "/webhooks/strava/",
        "/auth/strava/login",
        "/auth/strava/callback",
        "/v1/activities",
        "/v1/training/workouts/42/sets/abc",
        "/health/live",
        "/health/ready",
    ],
)
def test_public_routes_are_forwarded(path: str) -> None:
    assert gateway.is_routed(path)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/v1",
        "/v2/activities",
        "/webhooks/other",
        "/auth/other/login",
        "/healthz",
        "/_control/stats",
    ],
)
def test_everything_else_is_not(path: str) -> None:
    assert not gateway.is_routed(path)


def test_docs_only_with_expose_docs() -> None:
    assert gateway.is_routed("/docs", {"EXPOSE_DOCS": "true"})
    assert gateway.is_routed("/openapi.json", {"EXPOSE_DOCS": "true"})
    assert not gateway.is_routed("/openapi.json", {"EXPOSE_DOCS": "yes"})


def test_every_route_has_a_body_limit_a_matching_probe_and_auth_is_rate_limited() -> None:
    routes = gateway.load().routes
    for route in routes:
        assert route.max_body, route.name
        assert route.matches(route.probe), route.name
    assert {r.name for r in routes if r.rate_limit} == {"auth", "account"}
    for probe in gateway.load().blocked_probes:
        assert not gateway.is_routed(probe), probe


def test_sign_in_is_rate_limited_before_the_general_api_route_matches() -> None:
    names = [route.name for route in gateway.load().routes]
    assert names.index("account") < names.index("api")
    caddyfile = gateway.render()
    assert caddyfile.index("handle @account") < caddyfile.index("handle @api")


def test_the_acting_user_header_is_stripped_from_every_public_request() -> None:
    """ADR 0036: only the bot inside the compose network may send X-Acting-User."""
    caddyfile = gateway.render()
    site = caddyfile[caddyfile.index(":8080 {") :]
    assert site.index("request_header -X-Acting-User") < site.index("handle @")


def test_unknown_paths_fall_through_to_404_in_the_caddyfile() -> None:
    caddyfile = gateway.render()
    assert caddyfile.rstrip().endswith("handle {\n\t\trespond 404\n\t}\n}")
    assert "admin off" in caddyfile
    assert "metrics" not in caddyfile


@pytest.mark.parametrize(
    ("uri", "logged"),
    [
        (
            "/webhooks/strava?hub.mode=subscribe&hub.verify_token=s3cret&hub.challenge=x",
            "/webhooks/strava",
        ),
        ("/webhooks/strava/?hub.verify_token=s3cret", "/webhooks/strava/"),
        ("/webhooks/strava", "/webhooks/strava"),
        ("/v1/activities?limit=1", "/v1/activities?limit=1"),
    ],
)
def test_the_access_log_drops_the_webhook_query_string(uri: str, logged: str) -> None:
    """The same substitution Caddy's regexp log filter makes (RE2 and `re` agree on it)."""
    assert re.sub(gateway.WEBHOOK_QUERY_RE, r"\1", uri) == logged


def test_both_loggers_filter_the_query_and_the_api_key() -> None:
    caddyfile = gateway.render()
    assert caddyfile.count(f"request>uri regexp {gateway.WEBHOOK_QUERY_RE} $1") == 2
    assert caddyfile.count("request>headers>X-Api-Key delete") == 2
    assert "log default {" in caddyfile
