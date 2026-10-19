"""P8.10, ADR 0038: progress statistics over a hand-checked dataset in two time zones.

"Now" is Wednesday 28 Oct 2026, three days after Europe's DST change (25 Oct). A Berlin user
(UTC+2 until the change, UTC+1 after) and a New York user (UTC-4) have activities at the same
instants, which fall into different local weeks.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import Account, create_user, signed_in
from tests.support.factories import create_athlete
from tests.support.stats_data import Lift, Seeder
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
INSTANTS = (
    datetime(2026, 10, 18, 21, 30, tzinfo=UTC),  # Berlin Sun 18 Oct 23:30 | NY Sun 17:30
    datetime(2026, 10, 18, 22, 30, tzinfo=UTC),  # Berlin Mon 19 Oct 00:30 | NY Sun 18:30
    datetime(2026, 10, 25, 22, 30, tzinfo=UTC),  # Berlin Sun 25 Oct 23:30 | NY Sun 18:30
    datetime(2026, 10, 25, 23, 30, tzinfo=UTC),  # Berlin Mon 26 Oct 00:30 | NY Sun 19:30
)
W1 = datetime(2026, 10, 13, 16, 0, tzinfo=UTC)
W2 = datetime(2026, 10, 20, 16, 0, tzinfo=UTC)
W3 = datetime(2026, 10, 22, 16, 0, tzinfo=UTC)


@dataclass(frozen=True)
class People:
    berlin: Account
    new_york: Account


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


async def _seed_berlin(seed: Seeder) -> None:
    for instant in INSTANTS:
        seed.activity(instant, heartrate=150.0)
    # Monday and Thursday, 2 x 3 sets each, since 1 Oct.
    plan = [
        (0, [("bench-press", 3), ("back-squat", 3)]),
        (3, [("bench-press", 3), ("deadlift", 3)]),
    ]
    day_a, day_b = await seed.program(datetime(2026, 10, 1, tzinfo=UTC), plan)
    await seed.workout(
        W1,
        [
            Lift("bench-press", 10, 40, warmup=True),
            Lift("bench-press", 5, 100),
            Lift("bench-press", 15, 60),
        ],
    )
    await seed.workout(
        W2, [Lift("bench-press", 5, 100), Lift("back-squat", 5, 120)], program_day_id=day_a
    )
    await seed.workout(
        W3, [Lift("bench-press", 3, 105), Lift("bench-press", 2, 110)], program_day_id=day_b
    )
    seed.target(2500)
    await seed.meal(date(2026, 10, 19), kcal_100g=200, grams=1000, protein=10)
    await seed.meal(date(2026, 10, 20), kcal_100g=300, grams=1000)
    await seed.meal(date(2026, 10, 20), kcal_100g=500, grams=100, sugars=60, group="sweets")
    await seed.meal(date(2026, 10, 21), kcal_100g=50, grams=200, sugars=30, group="fruit")
    for day, kg in ((19, 80.0), (22, 79.7), (25, 79.4)):
        seed.weight(date(2026, 10, day), kg)
    for day in range(19, 28):
        seed.checkin(date(2026, 10, day))


@pytest.fixture
async def people(sessionmaker: async_sessionmaker[AsyncSession]) -> People:
    berlin = await create_user(sessionmaker, "berlin@example.com", timezone="Europe/Berlin")
    new_york = await create_user(sessionmaker, "nyc@example.com", timezone="America/New_York")
    for account, strava_id in ((berlin, 5101), (new_york, 5102)):
        athlete = await create_athlete(sessionmaker, strava_id, user_id=account.id)
        async with sessionmaker.begin() as session:
            seed = Seeder(session, account.id, athlete)
            if account is berlin:
                await _seed_berlin(seed)
            else:
                for instant in INSTANTS:
                    seed.activity(instant)
    return People(berlin, new_york)


async def _get(api: httpx.AsyncClient, path: str, **params: object) -> dict[str, Any]:
    response = await api.get(path, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _count(summary: dict[str, Any]) -> tuple[int, int | None]:
    count = summary["endurance"]["totals"]["count"]
    return count["value"], count["previous"]


async def test_weeks_are_local_on_both_sides_of_the_dst_change(
    app: FastAPI, people: People
) -> None:
    async with signed_in(app, people.berlin) as api:
        last_week = await _get(api, "/v1/stats/summary", period="last_week")
        this_week = await _get(api, "/v1/stats/summary", period="week")
    assert (last_week["window"]["from"], last_week["window"]["to"]) == ("2026-10-19", "2026-10-25")
    assert (last_week["previous"]["from"], last_week["previous"]["to"]) == (
        "2026-10-12",
        "2026-10-18",
    )
    assert _count(last_week) == (2, 1)
    assert last_week["totals"]["count"] == 2  # the classic field agrees
    assert _count(this_week) == (1, 1)  # Mon-Wed vs Mon-Wed of last week
    async with signed_in(app, people.new_york) as api:
        last_week = await _get(api, "/v1/stats/summary", period="last_week")
        this_week = await _get(api, "/v1/stats/summary", period="week")
        weekly = await _get(api, "/v1/stats/weekly", **{"from": "2026-10-12", "to": "2026-10-25"})
    assert _count(last_week) == (2, 2)
    assert _count(this_week) == (0, 0)
    assert [w["count"] for w in weekly["weeks"]] == [2, 2]


async def test_endurance_averages_per_sport_group(app: FastAPI, people: People) -> None:
    async with signed_in(app, people.berlin) as api:
        summary = await _get(api, "/v1/stats/summary", period="last_week")
    (run,) = summary["endurance"]["by_group"]
    assert run["group"] == "run"
    assert run["distance_m"]["value"] == 10000.0
    assert run["average_speed_mps"]["value"] == pytest.approx(5000 / 1500)
    assert run["average_heartrate"]["value"] == 150.0
    assert summary["endurance"]["longest"][0]["group"] == "run"
    assert summary["endurance"]["fastest"][0]["distance_m"] == 5000.0


async def test_strength_e1rm_prs_and_volume(app: FastAPI, people: People) -> None:
    async with signed_in(app, people.berlin) as api:
        summary = await _get(api, "/v1/stats/summary", period="last_week")
        prs = await _get(api, "/v1/stats/prs")
        last_week_prs = await _get(api, "/v1/stats/prs", period="last_week")
    strength = summary["strength"]
    assert (strength["sessions"]["value"], strength["sessions"]["previous"]) == (2, 1)
    # Working sets only: the 40 kg warm-up never counts.
    assert (strength["sets"]["value"], strength["sets"]["previous"]) == (4, 2)
    assert (strength["reps"]["value"], strength["reps"]["previous"]) == (15, 20)
    assert (strength["tonnage_kg"]["value"], strength["tonnage_kg"]["previous"]) == (1635, 1400)
    assert strength["tonnage_kg"]["change_pct"] == pytest.approx(16.8)
    # PRs: bench in W1 (first), squat in W2 (first), bench in W3 (117.33 > 116.67).
    assert (strength["pr_count"]["value"], strength["pr_count"]["previous"]) == (2, 1)
    bench = next(e for e in strength["by_exercise"] if e["name"] == "Bench Press")
    # 60 x 15 would be 90 kg e1RM, but sets above 10 reps are ignored.
    assert bench["best_e1rm_kg"]["value"] == 117.33
    assert bench["best_e1rm_kg"]["previous"] == 116.67
    assert {m["muscle"] for m in strength["by_muscle"]} == {"chest", "quads"}
    assert [(r["name"], r["e1rm_kg"], r["previous_kg"]) for r in prs["records"]] == [
        ("Bench Press", 117.33, 116.67),
        ("Back Squat", 140.0, None),
        ("Bench Press", 116.67, None),
    ]
    assert last_week_prs["count"] == 2
    # Planned: Mon 19 and Thu 22 Oct, 6 sets each; done: W2 and W3, 2 working sets each.
    assert strength["adherence"] == {
        "program_id": strength["adherence"]["program_id"],
        "program_name": "Plan",
        "planned_sessions": 2,
        "done_sessions": 2,
        "planned_sets": 12,
        "done_sets": 4,
        "session_ratio": 1.0,
        "set_ratio": pytest.approx(1 / 3),
    }


async def test_nutrition_body_and_consistency(app: FastAPI, people: People) -> None:
    async with signed_in(app, people.berlin) as api:
        summary = await _get(api, "/v1/stats/summary", period="last_week")
    nutrition = summary["nutrition"]
    assert nutrition["logged_days"]["value"] == 3
    assert nutrition["avg_kcal"]["value"] == pytest.approx((2000 + 3500 + 100) / 3)
    assert nutrition["kcal_target"] == 2500
    assert nutrition["avg_protein_g"]["value"] == pytest.approx(100 / 3)
    # 60 g from sweets is over the 50 g limit; 60 g from fruit never counts.
    assert nutrition["days_over_sugar_limit"]["value"] == 1
    assert nutrition["logging_rate"]["value"] == pytest.approx(3 / 7)
    body = summary["body"]
    assert (body["first_kg"], body["last_kg"]) == (80.0, 79.4)
    assert body["change_kg"]["value"] == pytest.approx(-0.6)
    assert body["rate_kg_per_week"]["value"] == pytest.approx(-0.7)
    assert body["moving_average_kg"] == pytest.approx(79.7)
    assert body["body_fat_pct"] is None
    consistency = summary["consistency"]
    assert (consistency["active_days"]["value"], consistency["active_days"]["previous"]) == (4, 2)
    assert consistency["training_streak_weeks"] == 3
    assert consistency["checkin_streak_days"] == 9  # through yesterday; today is not over
    assert consistency["checkin_rate"]["value"] == 1.0
    assert consistency["checkin_rate"]["change_pct"] is None  # nothing the week before


async def test_series_and_heatmap(app: FastAPI, people: People) -> None:
    async with signed_in(app, people.berlin) as api:
        distance = await _get(api, "/v1/stats/series", metric="distance_m", period="last_week")
        weight = await _get(api, "/v1/stats/series", metric="weight_kg", period="last_week")
        kcal = await _get(api, "/v1/stats/series", metric="kcal", period="12m")
        heatmap = await _get(api, "/v1/stats/heatmap", year=2026)
    assert distance["bucket"] == "day"
    assert [p["value"] for p in distance["points"]] == [5000.0, 0, 0, 0, 0, 0, 5000.0]
    values = [(p["value"], p["moving_average"]) for p in weight["points"]]
    assert values[0] == (80.0, 80.0)
    assert values[1] == (None, None)
    assert values[6][0] == 79.4
    assert values[6][1] == pytest.approx(79.7)
    assert kcal["bucket"] == "month"
    assert kcal["target"] == 2500.0
    assert kcal["points"][-1]["value"] == pytest.approx(5600.0)
    # This year up to today (Berlin, Wed 28 Oct): never a future day.
    assert (heatmap["year"], heatmap["rolling"]) == (2026, False)
    assert heatmap["window"] == {"from": "2026-01-01", "to": "2026-10-28", "days": 301}
    assert len(heatmap["days"]) == 301
    assert heatmap["days"][-1]["day"] == "2026-10-28"
    days = {d["day"]: d for d in heatmap["days"]}
    assert (days["2026-10-20"]["sessions"], days["2026-10-20"]["value"]) == (1, 60.0)
    assert days["2026-10-19"]["value"] == 25.0  # one 1500 s run
    assert days["2026-10-19"]["checkin"] == "done"
    assert heatmap["max_value"] == 60.0


async def test_heatmap_is_the_last_12_months_or_a_whole_past_year(
    app: FastAPI, people: People
) -> None:
    async with signed_in(app, people.berlin) as api:
        rolling = await _get(api, "/v1/stats/heatmap")
        past = await _get(api, "/v1/stats/heatmap", year=2025)
        future = await api.get("/v1/stats/heatmap", params={"year": 2027})
    assert (rolling["year"], rolling["rolling"]) == (2026, True)
    assert rolling["window"] == {"from": "2025-10-29", "to": "2026-10-28", "days": 365}
    assert [d["day"] for d in (rolling["days"][0], rolling["days"][-1])] == [
        "2025-10-29",
        "2026-10-28",
    ]
    assert {d["day"]: d["value"] for d in rolling["days"]}["2026-10-19"] == 25.0
    assert (past["rolling"], past["window"]["from"], past["window"]["to"]) == (
        False,
        "2025-01-01",
        "2025-12-31",
    )
    assert len(past["days"]) == 365
    assert future.status_code == 400


async def test_an_empty_period_is_zeros_and_null_changes(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    fresh = await create_user(sessionmaker, "fresh@example.com")
    async with signed_in(app, fresh) as api:
        summary = await _get(api, "/v1/stats/summary", period="month")
        everything = await _get(api, "/v1/stats/summary", period="all")
    assert summary["endurance"]["totals"]["count"] == {
        "value": 0,
        "previous": 0,
        "change": 0,
        "change_pct": None,
    }
    assert summary["nutrition"]["avg_kcal"]["value"] is None
    assert summary["strength"]["adherence"] is None
    assert everything["previous"] is None
    assert everything["strength"]["sessions"]["previous"] is None


async def test_a_bad_period_is_400(app: FastAPI, people: People) -> None:
    async with signed_in(app, people.berlin) as api:
        missing = await api.get("/v1/stats/summary", params={"period": "custom"})
        reversed_range = await api.get(
            "/v1/stats/prs", params={"period": "custom", "from": "2026-10-10", "to": "2026-10-01"}
        )
        old_style = await api.get(
            "/v1/stats/summary", params={"from": "2026-01-02", "to": "2026-01-01"}
        )
    assert missing.status_code == reversed_range.status_code == old_style.status_code == 400
