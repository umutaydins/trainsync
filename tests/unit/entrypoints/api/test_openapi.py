import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[4]
TAGS = {
    "auth",
    "webhooks",
    "activities",
    "stats",
    "sync",
    "health",
    "training",
    "nutrition",
    "chats",
    "me",
    "admin",
}
# Reachable without signing in.
PUBLIC_V1 = {
    "GET /v1/auth/registration",
    "POST /v1/auth/register",
    "POST /v1/auth/login",
    "POST /v1/auth/reset",
}


@pytest.fixture
def spec(settings: Settings) -> dict[str, Any]:
    return create_app(settings).openapi()


def _operations(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"{method.upper()} {path}", op)
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
    ]


def _has_example(content: dict[str, Any], schemas: dict[str, Any]) -> bool:
    for media in content.values():
        if "example" in media or "examples" in media:
            return True
        ref = media.get("schema", {}).get("$ref", "")
        if ref and "examples" in schemas[ref.rsplit("/", 1)[-1]]:
            return True
    return False


def test_every_operation_has_summary_tag_and_examples(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    problems = []
    for name, op in _operations(spec):
        if not op.get("summary"):
            problems.append(f"{name}: no summary")
        if not set(op.get("tags", [])) & TAGS:
            problems.append(f"{name}: no known tag")
        body = op.get("requestBody", {}).get("content")
        if body and not _has_example(body, schemas):
            problems.append(f"{name}: request body without example")
        for code, response in op["responses"].items():
            if "content" in response and not _has_example(response["content"], schemas):
                problems.append(f"{name}: {code} response without example")
    assert problems == []


def test_every_endpoint_is_documented(spec: dict[str, Any]) -> None:
    assert {name for name, _ in _operations(spec)} == {
        "GET /health/live",
        "GET /health/ready",
        "GET /auth/strava/login",
        "GET /auth/strava/callback",
        "GET /webhooks/strava",
        "POST /webhooks/strava",
        "GET /v1/auth/registration",
        "POST /v1/auth/register",
        "POST /v1/auth/login",
        "POST /v1/auth/logout",
        "POST /v1/auth/reset",
        "GET /v1/me",
        "PATCH /v1/me",
        "POST /v1/me/password",
        "GET /v1/me/sessions",
        "DELETE /v1/me/sessions/{session_id}",
        "POST /v1/admin/invites",
        "GET /v1/admin/invites",
        "DELETE /v1/admin/invites/{invite_id}",
        "GET /v1/admin/users",
        "POST /v1/admin/users/{user_id}/reset-link",
        "GET /v1/activities",
        "GET /v1/activities/{strava_activity_id}",
        "GET /v1/stats/weekly",
        "GET /v1/stats/summary",
        "GET /v1/sync/status",
        "GET /v1/chats/{chat_id}/settings",
        "PUT /v1/chats/{chat_id}/settings",
        "GET /v1/checkins",
        "GET /v1/checkins/summary",
        "GET /v1/checkins/{day}",
        "PUT /v1/checkins/{day}",
        "GET /v1/training/body-metrics",
        "PUT /v1/training/body-metrics/{day}",
        "GET /v1/training/exercises",
        "POST /v1/training/exercises",
        "PATCH /v1/training/exercises/{exercise_id}",
        "GET /v1/training/exercises/{exercise_id}/progress",
        "GET /v1/training/programs",
        "POST /v1/training/programs",
        "GET /v1/training/programs/active",
        "GET /v1/training/programs/active/next-day",
        "DELETE /v1/training/programs/{program_id}",
        "GET /v1/training/programs/{program_id}",
        "PUT /v1/training/programs/{program_id}",
        "POST /v1/training/programs/{program_id}/activate",
        "GET /v1/training/plates",
        "POST /v1/training/programs/generate",
        "GET /v1/training/prs",
        "GET /v1/training/volume/weekly",
        "GET /v1/training/workouts",
        "PUT /v1/training/workouts/{client_id}",
        "DELETE /v1/training/workouts/{workout_id}",
        "GET /v1/training/workouts/{workout_id}",
        "POST /v1/training/workouts/{workout_id}/finish",
        "DELETE /v1/training/workouts/{workout_id}/sets/{client_id}",
        "PUT /v1/training/workouts/{workout_id}/sets/{client_id}",
        "GET /v1/nutrition/foods",
        "POST /v1/nutrition/foods",
        "GET /v1/nutrition/foods/lookup",
        "PATCH /v1/nutrition/foods/{food_id}",
        "PUT /v1/nutrition/foods/{food_id}/favorite",
        "DELETE /v1/nutrition/foods/{food_id}/favorite",
        "GET /v1/nutrition/log",
        "PUT /v1/nutrition/log/{client_id}",
        "DELETE /v1/nutrition/log/{client_id}",
        "GET /v1/nutrition/profile",
        "PUT /v1/nutrition/profile",
        "GET /v1/nutrition/summary",
        "GET /v1/nutrition/summary/weekly",
    }


def test_v1_routes_declare_their_auth_and_401(spec: dict[str, Any]) -> None:
    """A session token or an API key (ADR 0034); the sign-in routes themselves are public."""
    for name, op in _operations(spec):
        if " /v1/" not in name or name in PUBLIC_V1:
            continue
        schemes = {scheme for requirement in op.get("security", []) for scheme in requirement}
        assert {"HTTPBearer", "APIKeyHeader"} <= schemes or schemes == {"APIKeyHeader"}, name
        assert "401" in op["responses"], name


def _export_script() -> ModuleType:
    path = REPO_ROOT / "scripts" / "export_openapi.py"
    module_spec = importlib.util.spec_from_file_location("export_openapi", path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_docs_openapi_json_is_current() -> None:
    script = _export_script()
    committed = (REPO_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8")
    assert committed == script.render(), "run: uv run python scripts/export_openapi.py"


async def test_docs_page_is_served(settings: Settings) -> None:
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        docs = await client.get("/docs")
        spec = await client.get("/openapi.json")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert spec.json()["paths"].keys() >= {"/v1/activities", "/webhooks/strava"}
