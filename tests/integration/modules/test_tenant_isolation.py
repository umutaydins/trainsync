"""P8.2, ADR 0035: no user can read or write another user's rows.

User A creates one of everything; user B then calls every user-owned route of the OpenAPI
document with A's ids and gets 404, and B's lists never show A's rows. The routes are walked
from the spec, so a new route with a path parameter fails here until it is classified.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import Account, create_user, signed_in
from tests.support.factories import create_athlete, strava_activity
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.activities.repository import ActivityRepository

DAY = "2026-10-18"
STARTED = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
PROFILE = {
    "sex": "female",
    "birth_year": 1990,
    "height_cm": 168,
    "activity_baseline": "light",
    "kcal_target": 2100,
}

# Routes with path parameters that are not about user data, and why.
NOT_USER_DATA = {
    "/auth/strava/callback": "the signed state names the user",
    "/v1/admin/invites/{invite_id}": "owner only (403 for users, tested in test_accounts)",
    "/v1/admin/users/{user_id}/reset-link": "owner only (403 for users)",
    "/v1/telegram/chats/{chat_id}": "service key only",
    "/v1/telegram/chats/{chat_id}/link": "service key only",
}
# PUTs keyed by a client id or a day create the caller's own row: B gets their own, A's is
# untouched (checked below).
CREATES_OWN = {
    ("PUT", "/v1/training/workouts/{client_id}"),
    ("PUT", "/v1/checkins/{day}"),
    ("PUT", "/v1/training/body-metrics/{day}"),
}


@dataclass
class Owned:
    """Ids of what user A created."""

    program_id: int
    workout_id: int
    workout_client_id: str
    set_client_id: str
    exercise_id: int
    bench_id: int  # built-in: B can use it too
    food_id: int
    log_client_id: str
    activity_id: int
    session_id: int


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


async def _ok(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


async def _create_everything(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], alice: Account
) -> Owned:
    bench = (await api.get("/v1/training/exercises", params={"q": "bench-press"})).json()
    bench_id = next(e["id"] for e in bench["items"] if e["slug"] == "bench-press")
    custom = await _ok(
        await api.post(
            "/v1/training/exercises",
            json={"name": "Alice press", "primary_muscle": "chest", "equipment": "dumbbell"},
        ),
        201,
    )
    planned = {"exercise_id": bench_id, "sets": 3, "rep_min": 5, "rep_max": 5}
    program = await _ok(
        await api.post(
            "/v1/training/programs",
            json={
                "name": "A's plan",
                "goal": "strength",
                "days": [{"name": "Day 1", "exercises": [{**planned, "rest_seconds": 90}]}],
            },
        ),
        201,
    )
    await _ok(await api.post(f"/v1/training/programs/{program['id']}/activate"))
    workout_client = str(uuid.uuid4())
    workout = await _ok(
        await api.put(
            f"/v1/training/workouts/{workout_client}", json={"started_at": STARTED.isoformat()}
        ),
        201,
    )
    set_client = str(uuid.uuid4())
    await _ok(
        await api.put(
            f"/v1/training/workouts/{workout['id']}/sets/{set_client}",
            json={
                "exercise_id": bench_id,
                "set_index": 0,
                "reps": 5,
                "weight_kg": "80",
                "completed_at": (STARTED + timedelta(minutes=5)).isoformat(),
            },
        ),
        201,
    )
    await _ok(await api.put(f"/v1/checkins/{DAY}", json={"status": "rest"}), 201)
    await _ok(await api.put(f"/v1/training/body-metrics/{DAY}", json={"weight_kg": 64.0}))
    food = await _ok(
        await api.post("/v1/nutrition/foods", json={"name": "Alice's granola", "kcal_100g": 450}),
        201,
    )
    log_client = str(uuid.uuid4())
    await _ok(
        await api.put(
            f"/v1/nutrition/log/{log_client}",
            json={"date": DAY, "meal": "breakfast", "food_id": food["id"], "grams": 60},
        ),
        201,
    )
    await _ok(await api.put("/v1/nutrition/profile", json=PROFILE))
    athlete = await create_athlete(sessionmaker, 3001, user_id=alice.id)
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(athlete, [strava_activity(777)])
    sessions = await _ok(await api.get("/v1/me/sessions"))
    return Owned(
        program_id=program["id"],
        workout_id=workout["id"],
        workout_client_id=workout_client,
        set_client_id=set_client,
        exercise_id=custom["id"],
        bench_id=bench_id,
        food_id=food["id"],
        log_client_id=log_client,
        activity_id=777,
        session_id=sessions["items"][0]["id"],
    )


def _path_values(owned: Owned, method: str, path: str) -> dict[str, object]:
    client_id = owned.set_client_id if "/sets/" in path else owned.workout_client_id
    if path.startswith("/v1/nutrition/log/"):
        client_id = owned.log_client_id
    return {
        "program_id": owned.program_id,
        "workout_id": owned.workout_id,
        "client_id": client_id,
        "exercise_id": owned.exercise_id,
        "food_id": owned.food_id,
        "strava_activity_id": owned.activity_id,
        "session_id": owned.session_id,
        "day": DAY,
    }


def _body(method: str, path: str, owned: Owned) -> dict[str, Any] | None:
    if method not in ("POST", "PUT", "PATCH"):
        return None
    if path.endswith("/sets/{client_id}"):
        return {
            "exercise_id": owned.bench_id,
            "set_index": 0,
            "reps": 5,
            "weight_kg": "1",
            "completed_at": STARTED.isoformat(),
        }
    if path == "/v1/training/programs/{program_id}":
        planned = {"exercise_id": owned.bench_id, "sets": 1, "rep_min": 5, "rep_max": 5}
        day = {"name": "x", "exercises": [{**planned, "rest_seconds": 60}]}
        return {"name": "x", "goal": "strength", "days": [day]}
    if path == "/v1/training/workouts/{client_id}":
        return {"started_at": STARTED.isoformat()}
    if path == "/v1/checkins/{day}":
        return {"status": "skipped"}
    if path == "/v1/training/body-metrics/{day}":
        return {"weight_kg": 90.0}
    if path == "/v1/nutrition/log/{client_id}":  # B may not log A's private food: 404
        return {"date": DAY, "meal": "lunch", "food_id": owned.food_id, "grams": 10}
    if path == "/v1/training/workouts/{workout_id}/finish":
        return {"ended_at": STARTED.isoformat()}
    return {"name": "stolen"} if method == "PATCH" else {}


def _user_routes(spec: dict[str, Any]) -> list[tuple[str, str]]:
    routes = []
    for path, operations in spec["paths"].items():
        if "{" not in path or path in NOT_USER_DATA:
            continue
        routes.extend((method.upper(), path) for method in operations)
    return sorted(routes)


async def test_user_b_gets_404_on_every_one_of_user_a_s_ids(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    async with signed_in(app, alice) as as_alice:
        owned = await _create_everything(as_alice, sessionmaker, alice)
    routes = _user_routes(app.openapi())
    assert len(routes) >= 20  # the walk really covers the API
    async with signed_in(app, bob) as as_bob:
        for method, template in routes:
            values = _path_values(owned, method, template)
            path = template.format(**values)
            response = await as_bob.request(method, path, json=_body(method, template, owned))
            if (method, template) in CREATES_OWN:
                assert response.status_code in (200, 201), (method, path, response.text)
                continue
            assert response.status_code == 404, (method, path, response.status_code, response.text)

    async with signed_in(app, alice) as as_alice:  # A's rows are all still A's and unchanged
        workout = await _ok(await as_alice.get(f"/v1/training/workouts/{owned.workout_id}"))
        assert [s["client_id"] for s in workout["sets"]] == [owned.set_client_id]
        assert (await _ok(await as_alice.get(f"/v1/checkins/{DAY}")))["status"] == "rest"
        log = await _ok(await as_alice.get("/v1/nutrition/log", params={"date": DAY}))
        assert [e["client_id"] for e in log["entries"]] == [owned.log_client_id]
        assert (await _ok(await as_alice.get("/v1/nutrition/profile")))["birth_year"] == 1990
        food = await _ok(await as_alice.get("/v1/nutrition/foods", params={"q": "granola"}))
        assert [f["name"] for f in food["items"]] == ["Alice's granola"]
        assert (await as_alice.get("/v1/me")).status_code == 200  # B could not end A's session


async def test_lists_never_show_another_user_s_rows(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    async with signed_in(app, alice) as as_alice:
        await _create_everything(as_alice, sessionmaker, alice)
    async with signed_in(app, bob) as as_bob:
        empty_lists = {
            "/v1/training/programs": "items",
            "/v1/training/workouts": "items",
            "/v1/training/body-metrics": "items",
            "/v1/training/prs": "items",
            "/v1/activities": "items",
            "/v1/checkins": "items",
        }
        for path, key in empty_lists.items():
            params = {"from": "2026-10-01", "to": "2026-10-31"} if "checkins" in path else None
            body = await _ok(await as_bob.get(path, params=params))
            assert body[key] == [], (path, body)
        foods = await _ok(await as_bob.get("/v1/nutrition/foods", params={"q": "granola"}))
        assert foods["items"] == []
        custom = await _ok(await as_bob.get("/v1/training/exercises", params={"q": "alice"}))
        assert custom["items"] == []
        log = await _ok(await as_bob.get("/v1/nutrition/log", params={"date": DAY}))
        assert log["entries"] == []
        assert (await as_bob.get("/v1/nutrition/profile")).status_code == 404
        assert (await as_bob.get("/v1/training/programs/active")).status_code == 404
        day = await _ok(await as_bob.get("/v1/nutrition/summary", params={"date": DAY}))
        assert day["entry_count"] == 0
        status = await _ok(await as_bob.get("/v1/sync/status"))
        assert status["athletes"] == []
        stats = await _ok(
            await as_bob.get("/v1/stats/summary", params={"from": "2026-01-01", "to": DAY})
        )
        assert stats["totals"]["count"] == 0


async def test_the_same_client_ids_and_days_are_independent_per_user(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """ADR 0035: per-user unique keys; a retried PUT never lands in someone else's row."""
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    client_id = str(uuid.uuid4())
    started = {"started_at": STARTED.isoformat()}
    async with signed_in(app, alice) as as_alice:
        mine = await _ok(
            await as_alice.put(f"/v1/training/workouts/{client_id}", json=started), 201
        )
        await _ok(await as_alice.put(f"/v1/checkins/{DAY}", json={"status": "done"}), 201)
    async with signed_in(app, bob) as as_bob:
        theirs = await _ok(
            await as_bob.put(f"/v1/training/workouts/{client_id}", json=started), 201
        )
        await _ok(await as_bob.put(f"/v1/checkins/{DAY}", json={"status": "sick_or_injured"}), 201)
    assert mine["id"] != theirs["id"]
    async with signed_in(app, alice) as as_alice:
        assert (await _ok(await as_alice.get(f"/v1/checkins/{DAY}")))["status"] == "done"
