"""P6.3 through the API: program preview and save, plates, progression suggestions on start."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.settings import Settings
from trainsync.db.repositories.training import ExerciseRepository
from trainsync.main import create_app

pytestmark = pytest.mark.integration

KEY = {"X-API-Key": "test-api-key"}
NOW = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)


@pytest.fixture
async def api(integration_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    settings = integration_settings.model_copy(
        update={"progression_lower_body_increment_kg": Decimal(10)}
    )
    app: FastAPI = create_app(settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api", headers=KEY
        ) as client:
            yield client


async def test_generate_preview_then_save(api: httpx.AsyncClient) -> None:
    request = {
        "days_per_week": 4,
        "goal": "hypertrophy",
        "equipment": ["barbell", "dumbbell"],
        "session_minutes": 60,
    }
    first = await api.post("/v1/training/programs/generate", json=request)
    second = await api.post("/v1/training/programs/generate", json=request)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    preview = first.json()
    assert preview["template"] == "upper_lower"
    assert [d["name"] for d in preview["days"]] == ["Upper A", "Lower A", "Upper B", "Lower B"]
    assert all(d["estimated_minutes"] <= 60 for d in preview["days"])
    assert preview["days"][0]["exercises"][0] == {
        "exercise_id": preview["program"]["days"][0]["exercises"][0]["exercise_id"],
        "slug": "bench-press",
        "name": "Bench Press",
        "role": "compound",
    }
    assert (await api.get("/v1/training/programs")).json()["items"] == []  # nothing saved

    saved = await api.post("/v1/training/programs", json=preview["program"])
    assert saved.status_code == 201
    body = saved.json()
    assert (body["goal"], body["days_per_week"]) == ("hypertrophy", 4)
    assert [len(d["exercises"]) for d in body["days"]] == [
        len(d["exercises"]) for d in preview["days"]
    ]

    unsupported = await api.post(
        "/v1/training/programs/generate", json={**request, "template": "push_pull_legs"}
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"] == "push_pull_legs takes 3 or 6 days a week"


async def test_plates(api: httpx.AsyncClient) -> None:
    exact = (await api.get("/v1/training/plates", params={"target": "102.5"})).json()
    assert exact == {
        "target_kg": 102.5,
        "bar_kg": 20.0,
        "per_side": [25.0, 15.0, 1.25],
        "achieved_kg": 102.5,
        "difference_kg": 0.0,
        "exact": True,
    }
    short = (await api.get("/v1/training/plates", params={"target": "101"})).json()
    assert (short["achieved_kg"], short["difference_kg"], short["exact"]) == (100.0, 1.0, False)
    light = (await api.get("/v1/training/plates", params={"target": "10"})).json()
    assert (light["per_side"], light["difference_kg"]) == ([], -10.0)
    assert (await api.get("/v1/training/plates", params={"target": "-1"})).status_code == 422


async def test_starting_a_workout_suggests_the_next_weights(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    slugs = ("bench-press", "back-squat", "barbell-row", "overhead-press")
    async with sessionmaker() as session:
        repo = ExerciseRepository(session)
        ids = {slug: e.id for slug in slugs if (e := await repo.by_slug(slug)) is not None}

    def planned(slug: str, **extra: Any) -> dict[str, Any]:
        return {
            "exercise_id": ids[slug],
            "sets": 3,
            "rep_min": 8,
            "rep_max": 12,
            "rest_seconds": 90,
            **extra,
        }

    program = await api.post(
        "/v1/training/programs",
        json={
            "name": "Test",
            "goal": "hypertrophy",
            "days": [
                {
                    "name": "Day",
                    "exercises": [
                        planned("bench-press"),
                        planned("back-squat"),
                        planned("barbell-row"),
                        planned("overhead-press", start_weight_kg=40),
                    ],
                }
            ],
        },
    )
    day_id = program.json()["days"][0]["id"]

    # Two earlier sessions: bench and squat hit 12s last time, rows missed 8 twice.
    history = [
        {"bench-press": ("77.5", 10), "back-squat": ("100", 10), "barbell-row": ("60", 7)},
        {"bench-press": ("80", 12), "back-squat": ("100", 12), "barbell-row": ("60", 6)},
    ]
    for days_ago, logged in zip((4, 2), history, strict=True):
        started = NOW - timedelta(days=days_ago)
        workout = (
            await api.post("/v1/training/workouts", json={"started_at": started.isoformat()})
        ).json()
        for slug, (weight, reps) in logged.items():
            for index in range(3):
                response = await api.put(
                    f"/v1/training/workouts/{workout['id']}/sets/{uuid.uuid4()}",
                    json={
                        "exercise_id": ids[slug],
                        "set_index": index,
                        "reps": reps,
                        "weight_kg": weight,
                        "completed_at": started.isoformat(),
                    },
                )
                assert response.status_code == 201

    today = (await api.post("/v1/training/workouts", json={"program_day_id": day_id})).json()
    suggestions = {p["exercise"]["slug"]: p["suggestion"] for p in today["planned"]}
    assert suggestions == {
        "bench-press": {"action": "increase", "weight_kg": 82.5, "previous_weight_kg": 80.0},
        # Lower body uses PROGRESSION_LOWER_BODY_INCREMENT_KG (10 in this test).
        "back-squat": {"action": "increase", "weight_kg": 110.0, "previous_weight_kg": 100.0},
        "barbell-row": {"action": "deload", "weight_kg": 53.75, "previous_weight_kg": 60.0},
        "overhead-press": {"action": "start", "weight_kg": 40.0, "previous_weight_kg": None},
    }
    # The same plan comes back when the workout is fetched again.
    again = (await api.get(f"/v1/training/workouts/{today['id']}")).json()
    assert [p["suggestion"] for p in again["planned"]] == [
        p["suggestion"] for p in today["planned"]
    ]
