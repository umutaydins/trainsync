import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from trainsync.core.settings import Settings
from trainsync.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
TAGS = {"auth", "webhooks", "activities", "stats", "sync", "health", "nutrition"}


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
        "GET /v1/activities",
        "GET /v1/activities/{strava_activity_id}",
        "GET /v1/stats/weekly",
        "GET /v1/stats/summary",
        "GET /v1/sync/status",
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


def test_v1_routes_declare_api_key_and_401(spec: dict[str, Any]) -> None:
    for name, op in _operations(spec):
        if " /v1/" in name:
            assert op.get("security") == [{"APIKeyHeader": []}], name
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
