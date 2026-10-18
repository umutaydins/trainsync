"""A stubbed trainsync API for bot unit tests (respx), with just enough state to prove
idempotency: sets and food log entries are stored by client id, like the real API.

The real API's idempotency is proven against Postgres in tests/integration; here the point is
that the bot sends the same client ids again on a redelivered update.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import respx

API = "http://trainsync-api"

EXERCISES: list[dict[str, Any]] = [
    {
        "id": 20,
        "slug": "bench-press",
        "name": "Bench Press",
        "primary_muscle": "chest",
        "secondary_muscles": ["triceps"],
        "equipment": "barbell",
        "movement_pattern": "horizontal_push",
        "is_custom": False,
    },
    {
        "id": 21,
        "slug": "incline-bench-press",
        "name": "Incline Bench Press",
        "primary_muscle": "chest",
        "secondary_muscles": [],
        "equipment": "barbell",
        "movement_pattern": "horizontal_push",
        "is_custom": False,
    },
    {
        "id": 22,
        "slug": "dumbbell-bench-press",
        "name": "Dumbbell Bench Press",
        "primary_muscle": "chest",
        "secondary_muscles": [],
        "equipment": "dumbbell",
        "movement_pattern": "horizontal_push",
        "is_custom": False,
    },
    {
        "id": 1,
        "slug": "back-squat",
        "name": "Back Squat",
        "primary_muscle": "quads",
        "secondary_muscles": ["glutes"],
        "equipment": "barbell",
        "movement_pattern": "squat",
        "is_custom": False,
    },
    {
        "id": 8,
        "slug": "deadlift",
        "name": "Deadlift",
        "primary_muscle": "hamstrings",
        "secondary_muscles": [],
        "equipment": "barbell",
        "movement_pattern": "hinge",
        "is_custom": False,
    },
    {
        "id": 38,
        "slug": "pull-up",
        "name": "Pull-Up",
        "primary_muscle": "back",
        "secondary_muscles": ["biceps"],
        "equipment": "bodyweight",
        "movement_pattern": "vertical_pull",
        "is_custom": False,
    },
]
BY_ID = {e["id"]: e for e in EXERCISES}

FOODS: list[dict[str, Any]] = [
    {
        "id": 7,
        "name": "Rolled oats",
        "brand": None,
        "barcode": None,
        "kcal_100g": 372.0,
        "protein_100g": 13.5,
        "carbs_100g": 58.7,
        "fat_100g": 7.0,
        "source": "manual",
        "favorite": True,
    },
    {
        "id": 8,
        "name": "Greek yogurt",
        "brand": "Acme",
        "barcode": None,
        "kcal_100g": 97.0,
        "protein_100g": 9.0,
        "carbs_100g": 3.6,
        "fat_100g": 5.0,
        "source": "manual",
        "favorite": False,
    },
    {
        "id": 9,
        "name": "Greek yogurt 0%",
        "brand": None,
        "barcode": None,
        "kcal_100g": 57.0,
        "protein_100g": 10.0,
        "carbs_100g": 4.0,
        "fat_100g": 0.0,
        "source": "manual",
        "favorite": False,
    },
]


def planned(
    exercise_id: int, sets: int, rep_min: int, rep_max: int, weight: float | None
) -> dict[str, Any]:
    return {
        "exercise": BY_ID[exercise_id],
        "sets": sets,
        "rep_min": rep_min,
        "rep_max": rep_max,
        "rest_seconds": 120,
        "start_weight_kg": weight,
        "progression": "double",
        "last_performance": None,
        "suggestion": {
            "action": "start" if weight is None else "hold",
            "weight_kg": weight,
            "previous_weight_kg": weight,
        },
    }


@dataclass
class Workout:
    id: int
    started_at: datetime
    program_day_id: int | None = None
    ended_at: datetime | None = None
    sets: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class FakeApi:
    """State of the stubbed API; `router` serves it."""

    router: respx.MockRouter
    workouts: dict[int, Workout] = field(default_factory=dict)
    food_log: dict[str, dict[str, Any]] = field(default_factory=dict)
    body_metrics: dict[str, float] = field(default_factory=dict)
    checkins: dict[str, dict[str, Any]] = field(default_factory=dict)
    program: dict[str, Any] | None = None
    kcal_target: int | None = 2600
    streak: int = 0
    next_workout_id: int = 100
    started: int = 0
    put_set_calls: int = 0

    # ---------------------------------------------------------------- builders

    def with_program(self, day_id: int = 11, *exercises: dict[str, Any]) -> None:
        self.program = {
            "program_id": 3,
            "program_name": "Upper/Lower",
            "day_id": day_id,
            "day_index": 0,
            "day_name": "Upper A",
            "open_workout_id": None,
            "planned": list(exercises),
        }

    def all_sets(self) -> list[dict[str, Any]]:
        return [s for w in self.workouts.values() for s in w.sets.values()]

    def detail(self, workout: Workout) -> dict[str, Any]:
        sets = sorted(workout.sets.values(), key=lambda s: (s["completed_at"], s["set_index"]))
        working = [s for s in sets if not s["is_warmup"]]
        volume = sum(s["reps"] * s["weight_kg"] for s in working)
        records = (
            [
                {
                    "exercise_id": 20,
                    "exercise_name": "Bench Press",
                    "kind": "weight_for_reps",
                    "value": 82.5,
                    "previous": 80.0,
                    "reps": 5,
                }
            ]
            if any(s["weight_kg"] >= 82.5 and s["exercise_id"] == 20 for s in sets)
            else []
        )
        planned_list = (
            self.program["planned"]
            if self.program and workout.program_day_id == self.program["day_id"]
            else []
        )
        return {
            "id": workout.id,
            "program_day_id": workout.program_day_id,
            "program_day_name": "Upper A" if planned_list else None,
            "started_at": workout.started_at.isoformat(),
            "ended_at": workout.ended_at.isoformat() if workout.ended_at else None,
            "notes": "",
            "set_count": len(sets),
            "exercise_count": len({s["exercise_id"] for s in sets}),
            "volume_kg": volume,
            "planned": planned_list,
            "sets": sets,
            "records": records,
        }


def _json(request: httpx.Request) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(request.content)
    return body


def install(router: respx.MockRouter, clock: Any) -> FakeApi:
    """Mock every endpoint the bot calls on `router`; `clock()` is "now" for started workouts."""
    api = FakeApi(router)

    def exercises(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "").lower()
        items = [e for e in EXERCISES if q in e["name"].lower() or q in e["slug"]]
        return httpx.Response(200, json={"items": items})

    def next_day(request: httpx.Request) -> httpx.Response:
        if api.program is None:
            return httpx.Response(404, json={"detail": "no active program"})
        body = dict(api.program)
        open_ids = [
            w.id
            for w in api.workouts.values()
            if w.ended_at is None and w.program_day_id == api.program["day_id"]
        ]
        body["open_workout_id"] = open_ids[-1] if open_ids else None
        return httpx.Response(200, json=body)

    def workouts(request: httpx.Request) -> httpx.Response:
        items = sorted(api.workouts.values(), key=lambda w: (w.started_at, w.id), reverse=True)
        summaries = []
        for w in items:
            d = api.detail(w)
            for extra in ("planned", "sets", "records"):
                d.pop(extra)
            summaries.append(d)
        return httpx.Response(200, json={"items": summaries, "next_cursor": None})

    def start(request: httpx.Request) -> httpx.Response:
        body = _json(request)
        api.started += 1
        workout = Workout(
            id=api.next_workout_id,
            started_at=datetime.fromisoformat(body["started_at"]),
            program_day_id=body.get("program_day_id"),
        )
        api.next_workout_id += 1
        api.workouts[workout.id] = workout
        return httpx.Response(201, json=api.detail(workout))

    def workout_id_of(request: httpx.Request) -> int:
        match = re.search(r"/workouts/(\d+)", request.url.path)
        assert match is not None
        return int(match.group(1))

    def get_workout(request: httpx.Request) -> httpx.Response:
        workout = api.workouts.get(workout_id_of(request))
        if workout is None:
            return httpx.Response(404, json={"detail": "workout not found"})
        return httpx.Response(200, json=api.detail(workout))

    def put_set(request: httpx.Request) -> httpx.Response:
        api.put_set_calls += 1
        workout = api.workouts[workout_id_of(request)]
        cid = request.url.path.rsplit("/", 1)[1]
        uuid.UUID(cid)
        body = _json(request)
        created = cid not in workout.sets
        workout.sets[cid] = {
            "client_id": cid,
            "workout_id": workout.id,
            "exercise_id": body["exercise_id"],
            "set_index": body["set_index"],
            "reps": body["reps"],
            "weight_kg": float(body["weight_kg"]),
            "rpe": None,
            "is_warmup": False,
            "completed_at": body["completed_at"],
            "rest_seconds": None,
        }
        return httpx.Response(201 if created else 200, json=workout.sets[cid])

    def finish(request: httpx.Request) -> httpx.Response:
        workout = api.workouts[workout_id_of(request)]
        if workout.ended_at is None:
            workout.ended_at = datetime.fromisoformat(_json(request)["ended_at"])
        return httpx.Response(200, json=api.detail(workout))

    def plates(request: httpx.Request) -> httpx.Response:
        target = Decimal(request.url.params["target"])
        if target == Decimal("102.5"):
            body = {"per_side": [25.0, 15.0, 1.25], "achieved_kg": 102.5, "exact": True}
        elif target == Decimal(20):
            body = {"per_side": [], "achieved_kg": 20.0, "exact": True}
        else:
            body = {"per_side": [25.0], "achieved_kg": 70.0, "exact": False}
        body.update(
            target_kg=float(target),
            bar_kg=20.0,
            difference_kg=float(target) - body["achieved_kg"],  # type: ignore[operator]
        )
        return httpx.Response(200, json=body)

    def foods(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "").lower()
        items = [f for f in FOODS if q in f["name"].lower()]
        items.sort(key=lambda f: (not f["favorite"], f["name"].lower()))
        return httpx.Response(200, json={"items": items})

    def lookup(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [], "remote": "not_found"})

    def put_log(request: httpx.Request) -> httpx.Response:
        cid = request.url.path.rsplit("/", 1)[1]
        body = _json(request)
        food = next(f for f in FOODS if f["id"] == body["food_id"])
        created = cid not in api.food_log
        grams = float(body["grams"])
        api.food_log[cid] = {
            "client_id": cid,
            "date": body["date"],
            "meal": body["meal"],
            "food_id": food["id"],
            "food_name": food["name"],
            "brand": food["brand"],
            "grams": grams,
            "kcal": round(food["kcal_100g"] * grams / 100, 1),
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "created_at": "2026-10-18T07:00:00Z",
        }
        return httpx.Response(201 if created else 200, json=api.food_log[cid])

    def summary(request: httpx.Request) -> httpx.Response:
        day = request.url.params["date"]
        entries = [e for e in api.food_log.values() if e["date"] == day]
        intake = sum(e["kcal"] for e in entries)
        target = api.kcal_target
        return httpx.Response(
            200,
            json={
                "date": day,
                "intake_kcal": intake,
                "protein_g": 31.5,
                "carbs_g": 120.2,
                "fat_g": 20.0,
                "entry_count": len(entries),
                "macros_complete": len(entries) < 2,
                "kcal_target": target,
                "protein_target_g": None,
                "kcal_remaining": None if target is None else target - intake,
                "bmr_kcal": None,
                "baseline_kcal": None,
                "activity_baseline": None,
                "weight_kg": None,
                "weight_date": None,
                "estimate_unavailable_reason": "no_profile",
                "exercise_kcal": 0.0,
                "exercise_unknown_count": 0,
                "exercise_complete": True,
                "activities": [],
                "expenditure_kcal": None,
                "balance_kcal": None,
                "balance_complete": False,
            },
        )

    def body_metric(request: httpx.Request) -> httpx.Response:
        day = request.url.path.rsplit("/", 1)[1]
        api.body_metrics[day] = float(_json(request)["weight_kg"])
        return httpx.Response(200, json={"date": day, "weight_kg": api.body_metrics[day]})

    def get_checkin(request: httpx.Request) -> httpx.Response:
        day = request.url.path.rsplit("/", 1)[1]
        if day not in api.checkins:
            return httpx.Response(404, json={"detail": "no check-in for this date"})
        return httpx.Response(200, json=api.checkins[day])

    def put_checkin(request: httpx.Request) -> httpx.Response:
        day = request.url.path.rsplit("/", 1)[1]
        body = _json(request)
        created = day not in api.checkins
        stamp = clock().astimezone(UTC).isoformat()
        api.checkins[day] = {
            "date": day,
            "status": body["status"],
            "workout_id": body.get("workout_id"),
            "reason_note": body.get("reason_note"),
            "sleep_hours": body.get("sleep_hours"),
            "energy_1_5": body.get("energy_1_5"),
            "body_weight_kg": body.get("body_weight_kg"),
            "created_at": api.checkins.get(day, {}).get("created_at", stamp),
            "updated_at": stamp,
        }
        if body.get("body_weight_kg") is not None:
            api.body_metrics[day] = float(body["body_weight_kg"])
        return httpx.Response(201 if created else 200, json=api.checkins[day])

    def checkin_summary(request: httpx.Request) -> httpx.Response:
        to = request.url.params.get("to", date.today().isoformat())
        return httpx.Response(
            200,
            json={
                "from": to,
                "to": to,
                "current_streak": api.streak,
                "longest_streak": api.streak,
                "planned_days": 0,
                "planned_days_done": 0,
                "adherence": None,
                "counts": {},
            },
        )

    base = f"{API}/v1"
    router.get(f"{base}/training/exercises", name="exercises").mock(side_effect=exercises)
    router.get(f"{base}/training/programs/active/next-day", name="next_day").mock(
        side_effect=next_day
    )
    router.get(f"{base}/training/workouts", name="workouts").mock(side_effect=workouts)
    router.post(f"{base}/training/workouts", name="start").mock(side_effect=start)
    router.get(url__regex=rf"{base}/training/workouts/\d+$", name="workout").mock(
        side_effect=get_workout
    )
    router.put(url__regex=rf"{base}/training/workouts/\d+/sets/[0-9a-f-]+$", name="put_set").mock(
        side_effect=put_set
    )
    router.post(url__regex=rf"{base}/training/workouts/\d+/finish$", name="finish").mock(
        side_effect=finish
    )
    router.get(f"{base}/training/plates", name="plates").mock(side_effect=plates)
    router.put(url__regex=rf"{base}/training/body-metrics/[\d-]+$", name="body_metric").mock(
        side_effect=body_metric
    )
    router.get(f"{base}/nutrition/foods", name="foods").mock(side_effect=foods)
    router.get(f"{base}/nutrition/foods/lookup", name="lookup").mock(side_effect=lookup)
    router.put(url__regex=rf"{base}/nutrition/log/[0-9a-f-]+$", name="put_log").mock(
        side_effect=put_log
    )
    router.get(f"{base}/nutrition/summary", name="nutrition_summary").mock(side_effect=summary)
    router.get(f"{base}/checkins/summary", name="checkin_summary").mock(side_effect=checkin_summary)
    router.get(url__regex=rf"{base}/checkins/[\d-]+$", name="get_checkin").mock(
        side_effect=get_checkin
    )
    router.put(url__regex=rf"{base}/checkins/[\d-]+$", name="put_checkin").mock(
        side_effect=put_checkin
    )
    return api
