"""P6.2: the training API against Postgres, through the ASGI app."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.training.math import SetEntry, best_e1rm, e1rm, volume, weekly_muscle_volume
from trainsync.modules.training.models import Workout, WorkoutSet
from trainsync.modules.training.repository import ExerciseRepository

pytestmark = pytest.mark.integration

KEY = {"X-API-Key": "test-api-key"}
NOW = datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
T0 = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)  # a Monday


@pytest.fixture
async def api(integration_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api", headers=KEY
        ) as client:
            yield client


async def slug_ids(sessionmaker: async_sessionmaker[AsyncSession], *slugs: str) -> list[int]:
    async with sessionmaker() as session:
        repo = ExerciseRepository(session)
        found = [await repo.by_slug(slug) for slug in slugs]
    return [e.id for e in found if e is not None]


async def start(api: httpx.AsyncClient, **body: Any) -> dict[str, Any]:
    response = await api.put(f"/v1/training/workouts/{uuid.uuid4()}", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def set_body(exercise_id: int, index: int, reps: int, weight: str, **extra: Any) -> dict[str, Any]:
    return {
        "exercise_id": exercise_id,
        "set_index": index,
        "reps": reps,
        "weight_kg": weight,
        "completed_at": (T0 + timedelta(minutes=index)).isoformat(),
        **extra,
    }


async def log(api: httpx.AsyncClient, workout_id: int, body: dict[str, Any]) -> dict[str, Any]:
    response = await api.put(f"/v1/training/workouts/{workout_id}/sets/{uuid.uuid4()}", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def set_count(sessionmaker: async_sessionmaker[AsyncSession]) -> int | None:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(WorkoutSet))


async def test_same_put_twice_and_concurrently_stores_one_set(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    (bench,) = await slug_ids(sessionmaker, "bench-press")
    workout = await start(api)
    body = set_body(bench, 0, 8, "80", rpe=8.5, rest_seconds=120)
    url = f"/v1/training/workouts/{workout['id']}/sets/{uuid.uuid4()}"

    first = await api.put(url, json=body)
    second = await api.put(url, json=body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert first.json()["weight_kg"] == 80.0
    assert first.json()["rpe"] == 8.5
    assert await set_count(sessionmaker) == 1

    concurrent_url = f"/v1/training/workouts/{workout['id']}/sets/{uuid.uuid4()}"
    responses = await asyncio.gather(*(api.put(concurrent_url, json=body) for _ in range(5)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201]
    assert len({r.text for r in responses}) == 1
    assert await set_count(sessionmaker) == 2

    # A correction with the same id updates the set.
    fixed = await api.put(url, json={**body, "reps": 9})
    assert (fixed.status_code, fixed.json()["reps"]) == (200, 9)
    assert await set_count(sessionmaker) == 2

    other = await start(api)
    moved = await api.put(f"/v1/training/workouts/{other['id']}/sets/{url[-36:]}", json=body)
    assert moved.status_code == 409

    for _ in range(2):  # deleting is idempotent too
        assert (await api.delete(url)).status_code == 204
    assert await set_count(sessionmaker) == 1


async def test_starting_a_workout_is_idempotent(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    url = f"/v1/training/workouts/{uuid.uuid4()}"
    body = {"started_at": "2026-10-18T17:00:00Z", "notes": "gym"}

    first = await api.put(url, json=body)
    double_tap = await api.put(url, json=body)
    assert (first.status_code, double_tap.status_code) == (201, 200)
    assert first.json() == double_tap.json()
    assert first.json()["client_id"] == url[-36:]

    # A late retry with another body returns the workout as first started.
    late = await api.put(url, json={"started_at": "2026-10-18T17:05:00Z", "notes": "retry"})
    assert late.status_code == 200
    assert (late.json()["id"], late.json()["notes"]) == (first.json()["id"], "gym")

    concurrent = f"/v1/training/workouts/{uuid.uuid4()}"
    responses = await asyncio.gather(*(api.put(concurrent, json=body) for _ in range(5)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201]
    assert len({r.json()["id"] for r in responses}) == 1

    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Workout)) == 2
    # The old non-idempotent start is gone.
    assert (await api.post("/v1/training/workouts", json=body)).status_code == 405


@pytest.mark.parametrize(
    "change",
    [
        {"weight_kg": "80.1"},
        {"weight_kg": "500.25"},
        {"weight_kg": "-2.5"},
        {"reps": 101},
        {"reps": -1},
        {"rest_seconds": -1},
        {"rpe": 7.3},
        {"rpe": 0.5},
    ],
)
async def test_set_validation(
    api: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    change: dict[str, Any],
) -> None:
    (bench,) = await slug_ids(sessionmaker, "bench-press")
    workout = await start(api)
    response = await api.put(
        f"/v1/training/workouts/{workout['id']}/sets/{uuid.uuid4()}",
        json={**set_body(bench, 0, 8, "80"), **change},
    )
    assert response.status_code == 422


async def test_set_errors(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    (bench,) = await slug_ids(sessionmaker, "bench-press")
    workout = await start(api)
    body = set_body(bench, 0, 8, "80")
    missing = await api.put(f"/v1/training/workouts/999999/sets/{uuid.uuid4()}", json=body)
    assert missing.status_code == 404
    unknown = await api.put(
        f"/v1/training/workouts/{workout['id']}/sets/{uuid.uuid4()}",
        json={**body, "exercise_id": 999999},
    )
    assert unknown.status_code == 400
    assert (
        await api.delete(f"/v1/training/workouts/999999/sets/{uuid.uuid4()}")
    ).status_code == 404


async def create_program(
    api: httpx.AsyncClient, days: list[tuple[str, list[int]]]
) -> dict[str, Any]:
    body = {
        "name": "Upper/Lower",
        "goal": "hypertrophy",
        "days": [
            {
                "name": name,
                "exercises": [
                    {"exercise_id": e, "sets": 3, "rep_min": 8, "rep_max": 12, "rest_seconds": 90}
                    for e in exercises
                ],
            }
            for name, exercises in days
        ],
    }
    response = await api.post("/v1/training/programs", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_start_from_a_program_day_returns_the_plan_with_last_performance(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    bench, row, squat = await slug_ids(sessionmaker, "bench-press", "barbell-row", "back-squat")
    program = await create_program(api, [("Upper", [bench, row]), ("Lower", [squat])])
    upper = program["days"][0]

    earlier = await start(api, program_day_id=upper["id"], started_at=T0.isoformat())
    await log(api, earlier["id"], set_body(bench, 0, 12, "40", is_warmup=True))
    await log(api, earlier["id"], set_body(bench, 1, 10, "77.5", rpe=8))
    await log(api, earlier["id"], set_body(bench, 2, 9, "77.5"))
    finished = await api.post(f"/v1/training/workouts/{earlier['id']}/finish", json={})
    assert finished.json()["ended_at"] == "2026-10-18T18:00:00Z"

    today = await start(api, program_day_id=upper["id"])
    assert today["started_at"] == "2026-10-18T18:00:00Z"
    assert today["program_day_name"] == "Upper"
    planned = today["planned"]
    assert [p["exercise"]["slug"] for p in planned] == ["bench-press", "barbell-row"]
    assert planned[0]["rep_min"] == 8
    last = planned[0]["last_performance"]
    assert last["workout_id"] == earlier["id"]
    assert [(s["reps"], s["weight_kg"], s["rpe"]) for s in last["sets"]] == [
        (10, 77.5, 8.0),
        (9, 77.5, None),
    ]
    assert planned[1]["last_performance"] is None

    # An empty workout can be finished; finishing again keeps the first end.
    empty = await start(api)
    first = await api.post(
        f"/v1/training/workouts/{empty['id']}/finish", json={"ended_at": NOW.isoformat()}
    )
    again = await api.post(
        f"/v1/training/workouts/{empty['id']}/finish",
        json={"ended_at": (NOW + timedelta(hours=1)).isoformat(), "notes": "rest day after all"},
    )
    assert first.status_code == again.status_code == 200
    assert (again.json()["ended_at"], again.json()["set_count"]) == ("2026-10-18T18:00:00Z", 0)
    assert again.json()["notes"] == "rest day after all"

    unknown_day = await api.put(
        f"/v1/training/workouts/{uuid.uuid4()}", json={"program_day_id": 999999}
    )
    assert unknown_day.status_code == 400
    early = await start(api, started_at=NOW.isoformat())
    too_early = await api.post(
        f"/v1/training/workouts/{early['id']}/finish",
        json={"ended_at": (NOW - timedelta(hours=1)).isoformat()},
    )
    assert too_early.status_code == 400


# Seeded bench and squat history: (days after T0, [(reps, weight, warm-up)]).
BENCH = [
    (0, [(10, "40", True), (8, "80", False), (8, "80", False), (6, "80", False)]),
    (3, [(5, "90", False), (5, "90", False)]),
    (8, [(8, "82.5", False), (15, "60", False)]),
]
SQUAT = [(3, [(5, "120", False), (5, "120", False)])]


async def seed_history(api: httpx.AsyncClient, bench: int, squat: int) -> dict[int, int]:
    """One workout per day offset; returns {day offset: workout id}."""
    workouts: dict[int, int] = {}
    for exercise, sessions in ((bench, BENCH), (squat, SQUAT)):
        for offset, sets in sessions:
            if offset not in workouts:
                started = (T0 + timedelta(days=offset)).isoformat()
                workouts[offset] = (await start(api, started_at=started))["id"]
            for index, (reps, weight, warmup) in enumerate(sets):
                await log(
                    api, workouts[offset], set_body(exercise, index, reps, weight, is_warmup=warmup)
                )
    return workouts


def entries(exercise: int, session: int, sets: list[tuple[int, str, bool]]) -> list[SetEntry]:
    return [SetEntry(session, exercise, r, Decimal(w), warm) for r, w, warm in sets]


async def test_progress_endpoints_match_the_training_math(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    bench, squat = await slug_ids(sessionmaker, "bench-press", "back-squat")
    workouts = await seed_history(api, bench, squat)

    progress = (await api.get(f"/v1/training/exercises/{bench}/progress")).json()
    sessions = progress["sessions"]
    assert [s["workout_id"] for s in sessions] == [workouts[o] for o, _ in BENCH]
    for got, (offset, sets) in zip(sessions, BENCH, strict=True):
        expected = entries(bench, offset, sets)
        assert Decimal(str(got["e1rm_kg"])) == best_e1rm(expected)
        assert Decimal(str(got["volume_kg"])) == volume(expected)
    # Hand-computed: 80 * (1 + 8/30) = 101.33; 90 * (1 + 5/30) = 105; 82.5 * (1 + 8/30) = 104.5.
    assert [s["e1rm_kg"] for s in sessions] == [101.33, 105.0, 104.5]
    assert [s["volume_kg"] for s in sessions] == [1760.0, 900.0, 1560.0]
    assert sessions[0]["best_set"] == {"reps": 8, "weight_kg": 80.0, "e1rm_kg": 101.33}
    assert sessions[0]["working_sets"] == 3
    ranged = await api.get(
        f"/v1/training/exercises/{bench}/progress",
        params={"from": "2026-10-01", "to": "2026-10-01"},
    )
    assert [s["workout_id"] for s in ranged.json()["sessions"]] == [workouts[3]]
    assert (await api.get("/v1/training/exercises/999999/progress")).status_code == 404

    weekly = (await api.get("/v1/training/volume/weekly", params={"from": "2026-09-01"})).json()
    expected_weeks = weekly_muscle_volume(
        [
            ((T0 + timedelta(days=offset)).date(), s)
            for exercise, history in ((bench, BENCH), (squat, SQUAT))
            for offset, sets in history
            for s in entries(exercise, offset, sets)
        ],
        {bench: "chest", squat: "quads"},
    )
    assert [
        (date.fromisoformat(w["week_start"]), w["muscle"], w["sets"], Decimal(str(w["volume_kg"])))
        for w in weekly["items"]
    ] == [(week, muscle, v.sets, v.volume_kg) for (week, muscle), v in expected_weeks.items()]
    assert weekly["items"][0] == {
        "week_start": "2026-09-28",
        "muscle": "chest",
        "sets": 5,
        "volume_kg": 2660.0,
    }
    bad = await api.get(
        "/v1/training/volume/weekly", params={"from": "2026-10-02", "to": "2026-10-01"}
    )
    assert bad.status_code == 400

    records = (await api.get("/v1/training/prs", params={"exercise_id": bench})).json()["items"]
    by_kind = {
        (r["kind"], r["reps"]): (r["value"], r["previous"], r["workout_id"]) for r in records
    }
    assert by_kind == {
        ("e1rm", None): (105.0, 101.33, workouts[3]),
        ("session_volume", None): (1760.0, None, workouts[0]),
        ("weight_for_reps", 5): (90.0, None, workouts[3]),
        ("weight_for_reps", 6): (80.0, None, workouts[0]),
        ("weight_for_reps", 8): (82.5, 80.0, workouts[8]),
        ("weight_for_reps", 15): (60.0, None, workouts[8]),
    }
    all_records = (await api.get("/v1/training/prs")).json()["items"]
    assert {r["exercise_name"] for r in all_records} == {"Bench Press", "Back Squat"}

    # The workout itself reports what it beat.
    detail = (await api.get(f"/v1/training/workouts/{workouts[8]}")).json()
    assert {(r["kind"], r["reps"], r["value"]) for r in detail["records"]} == {
        ("weight_for_reps", 8, 82.5),
        ("weight_for_reps", 15, 60.0),
    }
    assert detail["volume_kg"] == 1560.0
    assert e1rm(Decimal("82.5"), 8) == Decimal("104.50")
    assert (await api.get("/v1/training/workouts/999999")).status_code == 404


async def test_workout_list_is_keyset_paginated(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    (bench,) = await slug_ids(sessionmaker, "bench-press")
    ids = [
        (await start(api, started_at=(T0 + timedelta(days=d)).isoformat()))["id"] for d in range(5)
    ]
    await log(api, ids[0], set_body(bench, 0, 5, "100"))

    seen: list[dict[str, Any]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = (await api.get("/v1/training/workouts", params=params)).json()
        seen += body["items"]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert [w["id"] for w in seen] == list(reversed(ids))
    assert (seen[-1]["set_count"], seen[-1]["volume_kg"], seen[-1]["exercise_count"]) == (
        1,
        500.0,
        1,
    )
    assert (await api.get("/v1/training/workouts", params={"cursor": "nope"})).status_code == 400

    assert (await api.delete(f"/v1/training/workouts/{ids[0]}")).status_code == 204
    assert (await api.delete(f"/v1/training/workouts/{ids[0]}")).status_code == 404
    assert await set_count(sessionmaker) == 0


async def test_programs_crud_and_one_active(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    bench, squat = await slug_ids(sessionmaker, "bench-press", "back-squat")
    assert (await api.get("/v1/training/programs/active")).status_code == 404
    first = await create_program(api, [("Upper", [bench]), ("Lower", [squat])])
    second = await create_program(api, [("Full", [squat, bench])])
    assert (first["days_per_week"], first["active"], first["weeks"]) == (2, False, 8)
    assert first["days"][1]["exercises"][0]["exercise"]["slug"] == "back-squat"
    assert first["days"][0]["exercises"][0]["progression"] == "double"

    for program in (first, second, second):
        response = await api.post(f"/v1/training/programs/{program['id']}/activate")
        assert response.json()["active"] is True
    active = (await api.get("/v1/training/programs/active")).json()
    assert active["id"] == second["id"]
    listed = (await api.get("/v1/training/programs")).json()["items"]
    assert [(p["id"], p["active"]) for p in listed] == [(second["id"], True), (first["id"], False)]

    replaced = await api.put(
        f"/v1/training/programs/{first['id']}",
        json={
            "name": "Renamed",
            "goal": "strength",
            "weeks": 4,
            "days": [{"name": "Only", "exercises": []}],
        },
    )
    assert replaced.status_code == 200
    assert (replaced.json()["name"], replaced.json()["days_per_week"]) == ("Renamed", 1)
    got = (await api.get(f"/v1/training/programs/{first['id']}")).json()
    assert [d["name"] for d in got["days"]] == ["Only"]

    bad = {
        "name": "x",
        "goal": "general",
        "days": [
            {
                "name": "d",
                "exercises": [
                    {
                        "exercise_id": 999999,
                        "sets": 3,
                        "rep_min": 5,
                        "rep_max": 5,
                        "rest_seconds": 60,
                    }
                ],
            }
        ],
    }
    assert (await api.post("/v1/training/programs", json=bad)).status_code == 400
    assert (await api.put("/v1/training/programs/999999", json=bad)).status_code == 404
    inverted = {
        **bad,
        "days": [
            {
                "name": "d",
                "exercises": [
                    {
                        "exercise_id": bench,
                        "sets": 3,
                        "rep_min": 8,
                        "rep_max": 5,
                        "rest_seconds": 60,
                    }
                ],
            }
        ],
    }
    assert (await api.post("/v1/training/programs", json=inverted)).status_code == 422

    assert (await api.delete(f"/v1/training/programs/{first['id']}")).status_code == 204
    for path in (f"/v1/training/programs/{first['id']}",):
        assert (await api.get(path)).status_code == 404
        assert (await api.delete(path)).status_code == 404
        assert (await api.post(f"{path}/activate")).status_code == 404


async def test_exercise_library_and_custom_exercises(api: httpx.AsyncClient) -> None:
    found = (
        await api.get(
            "/v1/training/exercises",
            params={"q": "press", "muscle": "chest", "equipment": ["barbell"]},
        )
    ).json()
    assert {e["slug"] for e in found["items"]} >= {"bench-press", "incline-bench-press"}
    assert all(e["equipment"] == "barbell" for e in found["items"])

    created = await api.post(
        "/v1/training/exercises",
        json={"name": "Landmine Press!", "primary_muscle": "shoulders", "equipment": "barbell"},
    )
    assert created.status_code == 201
    custom = created.json()
    assert (custom["slug"], custom["is_custom"], custom["movement_pattern"]) == (
        "landmine-press",
        True,
        None,
    )
    duplicate = await api.post(
        "/v1/training/exercises",
        json={"name": "landmine press", "primary_muscle": "shoulders", "equipment": "barbell"},
    )
    assert duplicate.status_code == 409

    patched = await api.patch(
        f"/v1/training/exercises/{custom['id']}",
        json={
            "name": "Half-kneeling Landmine",
            "secondary_muscles": ["core"],
            "movement_pattern": "vertical_push",
        },
    )
    assert patched.status_code == 200
    assert (patched.json()["name"], patched.json()["slug"]) == (
        "Half-kneeling Landmine",
        "landmine-press",
    )
    assert patched.json()["secondary_muscles"] == ["core"]
    assert patched.json()["movement_pattern"] == "vertical_push"

    bench = next(e for e in found["items"] if e["slug"] == "bench-press")
    assert (
        await api.patch(f"/v1/training/exercises/{bench['id']}", json={"name": "x"})
    ).status_code == 409
    assert (await api.patch("/v1/training/exercises/999999", json={"name": "x"})).status_code == 404


async def test_body_metrics(api: httpx.AsyncClient) -> None:
    for day, weight in (("2026-10-12", 78.4), ("2026-10-14", 78.0), ("2026-10-12", 78.2)):
        response = await api.put(f"/v1/training/body-metrics/{day}", json={"weight_kg": weight})
        assert response.status_code == 200
    listed = (await api.get("/v1/training/body-metrics", params={"from": "2026-10-01"})).json()
    assert listed["items"] == [
        {"date": "2026-10-12", "weight_kg": 78.2},
        {"date": "2026-10-14", "weight_kg": 78.0},
    ]
    assert (
        await api.put("/v1/training/body-metrics/2026-10-12", json={"weight_kg": 0})
    ).status_code == 422
    assert (
        await api.get(
            "/v1/training/body-metrics", params={"from": "2026-10-02", "to": "2026-10-01"}
        )
    ).status_code == 400


async def test_training_requires_the_api_key(api: httpx.AsyncClient) -> None:
    response = await api.get("/v1/training/workouts", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
