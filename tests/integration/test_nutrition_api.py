"""P6.4: nutrition API against Postgres, Open Food Facts faked with respx."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.factories import create_athlete, strava_activity
from tests.support.openfoodfacts import (
    SEARCH,
    found,
    not_found,
    product,
    product_url,
    search_results,
)
from trainsync.core.settings import Settings
from trainsync.db.models import FoodLog
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.training import BodyMetricRepository
from trainsync.main import create_app

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "nutrition_energy.json").read_text(encoding="utf-8")
)
KEY = {"X-API-Key": "test-api-key"}
NOW = datetime(2026, 10, 14, 20, 0, tzinfo=UTC)  # a Wednesday
BASE = "/v1/nutrition"


@pytest.fixture
def settings_for_app(integration_settings: Settings) -> Settings:
    return integration_settings


@pytest.fixture
async def app(settings_for_app: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings_for_app)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api", headers=KEY) as client:
        yield client


async def _ok(response: httpx.Response, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


async def _food(api: httpx.AsyncClient, **body: Any) -> dict[str, Any]:
    result: dict[str, Any] = await _ok(await api.post(f"{BASE}/foods", json=body), 201)
    return result


async def _log(
    api: httpx.AsyncClient, food_id: int, grams: float, day: str = "2026-10-14", **extra: Any
) -> httpx.Response:
    body = {"date": day, "meal": "lunch", "food_id": food_id, "grams": grams, **extra}
    return await api.put(f"{BASE}/log/{uuid.uuid4()}", json=body)


# ---------------------------------------------------------------- energy balance fixture


async def _seed_fixture(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _ok(await api.put(f"{BASE}/profile", json=FIXTURE["profile"]))
    async with sessionmaker.begin() as session:
        metrics = BodyMetricRepository(session)
        for m in FIXTURE["body_metrics"]:
            await metrics.put(date.fromisoformat(m["date"]), Decimal(m["weight_kg"]))
    foods = {key: (await _food(api, **food))["id"] for key, food in FIXTURE["foods"].items()}
    for entry in FIXTURE["logs"]:
        await _ok(
            await _log(
                api, foods[entry["food"]], entry["grams"], entry["date"], meal=entry["meal"]
            ),
            201,
        )

    active = await create_athlete(sessionmaker, 1001)
    inactive = await create_athlete(sessionmaker, 1002, active=False)
    async with sessionmaker.begin() as session:
        repo = ActivityRepository(session)
        for a in FIXTURE["activities"]:
            fields = {
                k: a[k] for k in ("sport_type", "start_date", "calories", "kilojoules") if k in a
            }
            athlete = inactive if a.get("inactive_athlete") else active
            await repo.upsert_many(athlete, [strava_activity(a["id"], **fields)])
            if a.get("deleted"):
                await repo.soft_delete(a["id"])


def _comparable(day: dict[str, Any]) -> dict[str, Any]:
    """The API day with activities reduced to (id, kcal, known, source), like the fixture."""
    return {
        **day,
        "activities": [
            [a["strava_activity_id"], a["kcal"], a["kcal_known"], a["kcal_source"]]
            for a in day["activities"]
        ],
    }


async def test_summaries_and_energy_balance_match_hand_computed_fixture(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_fixture(api, sessionmaker)
    expected = FIXTURE["expected"]

    weekly = await _ok(
        await api.get(f"{BASE}/summary/weekly", params={"from": "2026-10-12", "to": "2026-10-14"})
    )
    assert (weekly["from"], weekly["to"]) == (expected["from"], expected["to"])
    assert [_comparable(d) for d in weekly["days"]] == expected["days"]
    assert weekly["totals"] == expected["totals"]

    for day in expected["days"]:
        single = await _ok(await api.get(f"{BASE}/summary", params={"date": day["date"]}))
        assert _comparable(single) == day

    log = await _ok(await api.get(f"{BASE}/log", params={"date": "2026-10-13"}))
    # Meal order (breakfast before snack), not insertion order.
    assert [(e["meal"], e["food_name"], e["kcal"]) for e in log["entries"]] == [
        ("breakfast", "Rolled oats", 190.0),
        ("snack", "Cola", 138.6),
    ]
    assert log["entries"][1]["protein_g"] is None  # unknown stays unknown


async def test_summary_without_profile_or_weight_says_why(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    day = await _ok(await api.get(f"{BASE}/summary"))
    assert day["date"] == "2026-10-14"  # today (UTC) from the injected clock
    assert day["estimate_unavailable_reason"] == "no_profile"
    assert (day["bmr_kcal"], day["baseline_kcal"], day["balance_kcal"]) == (None, None, None)
    assert (day["kcal_target"], day["kcal_remaining"], day["balance_complete"]) == (
        None,
        None,
        False,
    )

    await _ok(await api.put(f"{BASE}/profile", json=FIXTURE["profile"]))
    day = await _ok(await api.get(f"{BASE}/summary"))
    assert day["estimate_unavailable_reason"] == "no_body_weight"
    assert (day["bmr_kcal"], day["expenditure_kcal"], day["weight_kg"]) == (None, None, None)

    async with sessionmaker.begin() as session:  # a weight after the day does not count
        await BodyMetricRepository(session).put(date(2026, 10, 15), Decimal("80"))
    day = await _ok(await api.get(f"{BASE}/summary", params={"date": "2026-10-14"}))
    assert day["estimate_unavailable_reason"] == "no_body_weight"


async def test_weekly_defaults_to_current_iso_week_and_validates_range(
    api: httpx.AsyncClient,
) -> None:
    weekly = await _ok(await api.get(f"{BASE}/summary/weekly"))
    assert (weekly["from"], weekly["to"]) == ("2026-10-12", "2026-10-18")
    assert len(weekly["days"]) == 7
    assert weekly["totals"]["avg_intake_kcal"] is None
    assert weekly["totals"]["balance_kcal"] is None

    only_to = await _ok(await api.get(f"{BASE}/summary/weekly", params={"to": "2026-10-07"}))
    assert (only_to["from"], only_to["to"]) == ("2026-10-01", "2026-10-07")
    only_from = await _ok(await api.get(f"{BASE}/summary/weekly", params={"from": "2026-10-01"}))
    assert only_from["to"] == "2026-10-07"

    for params in (
        {"from": "2026-10-10", "to": "2026-10-01"},
        {"from": "2026-01-01", "to": "2026-06-01"},
    ):
        assert (await api.get(f"{BASE}/summary/weekly", params=params)).status_code == 400


# ---------------------------------------------------------------- food log


async def test_same_food_log_put_twice_stores_one_row(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    oats = await _food(api, **FIXTURE["foods"]["oats"])
    client_id = uuid.uuid4()
    body = {"date": "2026-10-14", "meal": "breakfast", "food_id": oats["id"], "grams": 80}

    first = await api.put(f"{BASE}/log/{client_id}", json=body)
    second = await api.put(f"{BASE}/log/{client_id}", json=body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert first.json()["kcal"] == 304.0

    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(FoodLog)) == 1

    edited = await _ok(await api.put(f"{BASE}/log/{client_id}", json={**body, "grams": 100}))
    assert (edited["grams"], edited["kcal"]) == (100.0, 380.0)
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(FoodLog)) == 1

    assert (await api.delete(f"{BASE}/log/{client_id}")).status_code == 204
    assert (await api.delete(f"{BASE}/log/{client_id}")).status_code == 404
    assert (await _ok(await api.get(f"{BASE}/log")))["entries"] == []


async def test_editing_a_food_does_not_change_past_days(api: httpx.AsyncClient) -> None:
    oats = await _food(api, **FIXTURE["foods"]["oats"])  # 380 kcal, 13 / 60 / 7 g per 100 g
    await _ok(await _log(api, oats["id"], 80, day="2026-10-13"), 201)
    before_log = await _ok(await api.get(f"{BASE}/log", params={"date": "2026-10-13"}))
    before_day = await _ok(await api.get(f"{BASE}/summary", params={"date": "2026-10-13"}))
    assert before_log["entries"][0]["kcal"] == 304.0
    assert before_day["intake_kcal"] == 304.0

    edit = {"kcal_100g": 400, "protein_100g": 10, "carbs_100g": None, "fat_100g": 8}
    await _ok(await api.patch(f"{BASE}/foods/{oats['id']}", json=edit))

    # The past day reads the values snapshotted when it was logged.
    after_log = await _ok(await api.get(f"{BASE}/log", params={"date": "2026-10-13"}))
    after_day = await _ok(await api.get(f"{BASE}/summary", params={"date": "2026-10-13"}))
    assert after_log == before_log
    assert after_day == before_day

    # A new entry takes the food's current values, unknown carbs included.
    new = await _ok(await _log(api, oats["id"], 50, day="2026-10-14"), 201)
    assert (new["kcal"], new["protein_g"], new["carbs_g"], new["fat_g"]) == (200.0, 5.0, None, 4.0)
    day = await _ok(await api.get(f"{BASE}/summary", params={"date": "2026-10-14"}))
    assert (day["intake_kcal"], day["macros_complete"]) == (200.0, False)


async def test_food_log_validation(api: httpx.AsyncClient) -> None:
    oats = await _food(api, **FIXTURE["foods"]["oats"])
    assert (await _log(api, 999_999, 50)).status_code == 404
    assert (await _log(api, oats["id"], 0)).status_code == 422
    assert (await _log(api, oats["id"], 50, meal="brunch")).status_code == 422
    bad_id = await api.put(
        f"{BASE}/log/not-a-uuid",
        json={"date": "2026-10-14", "meal": "lunch", "food_id": oats["id"], "grams": 1},
    )
    assert bad_id.status_code == 422


# ---------------------------------------------------------------- foods


async def test_create_search_update_and_favorite_foods(api: httpx.AsyncClient) -> None:
    oats = await _food(api, **FIXTURE["foods"]["oats"], brand="Acme", barcode="8690000000017")
    await _food(api, **FIXTURE["foods"]["chicken"])
    await _food(api, name="100% juice", kcal_100g=45)
    assert oats["source"] == "manual"
    assert oats["favorite"] is False

    async def names(**params: Any) -> list[str]:
        body = await _ok(await api.get(f"{BASE}/foods", params=params))
        return [f["name"] for f in body["items"]]

    assert await names() == ["100% juice", "Chicken breast", "Rolled oats"]
    assert await names(q="OATS") == ["Rolled oats"]
    assert await names(q="acme") == ["Rolled oats"]  # brand
    assert await names(q="8690000000017") == ["Rolled oats"]  # exact barcode
    assert await names(q="%") == ["100% juice"]  # LIKE wildcards are literal

    fav = await _ok(await api.put(f"{BASE}/foods/{oats['id']}/favorite"))
    assert fav["favorite"] is True
    assert (await _ok(await api.put(f"{BASE}/foods/{oats['id']}/favorite")))["favorite"] is True
    assert await names() == ["Rolled oats", "100% juice", "Chicken breast"]  # favorites first
    assert await names(favorites="true") == ["Rolled oats"]
    unfav = await _ok(await api.delete(f"{BASE}/foods/{oats['id']}/favorite"))
    assert unfav["favorite"] is False

    patched = await _ok(
        await api.patch(f"{BASE}/foods/{oats['id']}", json={"kcal_100g": 371.24, "fat_100g": None})
    )
    assert (patched["kcal_100g"], patched["fat_100g"], patched["protein_100g"]) == (
        371.2,
        None,
        13.0,
    )
    assert (await api.patch(f"{BASE}/foods/{oats['id']}", json={"name": None})).status_code == 400
    assert (await api.patch(f"{BASE}/foods/999999", json={"name": "x"})).status_code == 404
    assert (await api.put(f"{BASE}/foods/999999/favorite")).status_code == 404

    duplicate = await api.post(
        f"{BASE}/foods", json={"name": "Other", "kcal_100g": 1, "barcode": "8690000000017"}
    )
    assert duplicate.status_code == 409
    assert (
        await api.post(f"{BASE}/foods", json={"name": "x", "kcal_100g": 1200})
    ).status_code == 422


# ---------------------------------------------------------------- Open Food Facts


@respx.mock
async def test_barcode_lookup_caches_then_answers_locally(api: httpx.AsyncClient) -> None:
    barcode = "8690000000017"
    route = respx.get(product_url(barcode)).mock(return_value=found(product(code=barcode)))

    first = await _ok(await api.get(f"{BASE}/foods/lookup", params={"barcode": barcode}))
    assert first["remote"] == "ok"
    [food] = first["items"]
    assert (food["name"], food["brand"], food["kcal_100g"], food["source"]) == (
        "Rolled oats",
        "Acme",
        372.0,
        "openfoodfacts",
    )

    second = await _ok(await api.get(f"{BASE}/foods/lookup", params={"barcode": barcode}))
    assert second == {**first, "remote": "cached"}
    assert route.call_count == 1

    # A cached product can be logged like any other food.
    assert (await _log(api, food["id"], 40)).status_code == 201


@respx.mock
async def test_lookup_degrades_gracefully_on_timeout(api: httpx.AsyncClient) -> None:
    await _food(api, name="Oat bar", kcal_100g=410)
    respx.get(SEARCH).mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get(product_url("5000000000001")).mock(side_effect=httpx.ConnectTimeout("slow"))

    by_name = await _ok(await api.get(f"{BASE}/foods/lookup", params={"q": "oat"}))
    assert by_name["remote"] == "unavailable"
    assert [f["name"] for f in by_name["items"]] == ["Oat bar"]  # local results still come

    by_code = await _ok(await api.get(f"{BASE}/foods/lookup", params={"barcode": "5000000000001"}))
    assert by_code == {"items": [], "remote": "unavailable"}


@respx.mock
async def test_name_lookup_merges_local_and_remote_and_keeps_user_edits(
    api: httpx.AsyncClient,
) -> None:
    local = await _food(api, name="Oat bar", kcal_100g=410)
    respx.get(SEARCH).mock(
        return_value=search_results(
            product(code="1111111111111", name="Oat milk", **{"energy-kcal_100g": 46}),
            product(code="2222222222222", name="Porridge", **{"energy-kcal_100g": 360}),
        )
    )
    body = await _ok(await api.get(f"{BASE}/foods/lookup", params={"q": "oat"}))
    assert body["remote"] == "ok"
    # Local matches first (now including the cached "Oat milk"), then other remote hits.
    assert [f["name"] for f in body["items"]] == ["Oat bar", "Oat milk", "Porridge"]
    assert body["items"][0]["id"] == local["id"]
    milk = body["items"][1]

    # The user corrects a cached product: it becomes manual and a later lookup leaves it alone.
    edited = await _ok(await api.patch(f"{BASE}/foods/{milk['id']}", json={"kcal_100g": 50}))
    assert edited["source"] == "manual"
    again = await _ok(await api.get(f"{BASE}/foods/lookup", params={"q": "oat"}))
    assert next(f for f in again["items"] if f["id"] == milk["id"])["kcal_100g"] == 50.0
    assert len({f["id"] for f in again["items"]}) == 3  # cached, not duplicated


@respx.mock
async def test_lookup_not_found_and_bad_requests(api: httpx.AsyncClient) -> None:
    respx.get(product_url("4000000000002")).mock(return_value=not_found("4000000000002"))
    body = await _ok(await api.get(f"{BASE}/foods/lookup", params={"barcode": "4000000000002"}))
    assert body == {"items": [], "remote": "not_found"}

    assert (await api.get(f"{BASE}/foods/lookup")).status_code == 400
    both = {"barcode": "4000000000002", "q": "oat"}
    assert (await api.get(f"{BASE}/foods/lookup", params=both)).status_code == 400
    assert (await api.get(f"{BASE}/foods/lookup", params={"barcode": "12ab"})).status_code == 422


class TestLookupDisabled:
    @pytest.fixture
    def settings_for_app(self, integration_settings: Settings) -> Settings:
        return integration_settings.model_copy(update={"openfoodfacts_enabled": False})

    @respx.mock
    async def test_disabled_lookup_never_calls_out(self, api: httpx.AsyncClient) -> None:
        await _food(api, name="Oat bar", kcal_100g=410)
        by_name = await _ok(await api.get(f"{BASE}/foods/lookup", params={"q": "oat"}))
        assert by_name["remote"] == "disabled"
        assert [f["name"] for f in by_name["items"]] == ["Oat bar"]
        by_code = await _ok(await api.get(f"{BASE}/foods/lookup", params={"barcode": "12345678"}))
        assert by_code == {"items": [], "remote": "disabled"}
        assert respx.calls.call_count == 0


# ---------------------------------------------------------------- profile


async def test_profile_round_trip_and_target_below_bmr_warning(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    assert (await api.get(f"{BASE}/profile")).status_code == 404

    stored = await _ok(
        await api.put(f"{BASE}/profile", json={**FIXTURE["profile"], "kcal_target": 1500})
    )
    assert stored["bmr_kcal"] is None
    assert stored["estimate_unavailable_reason"] == "no_body_weight"
    assert stored["warning"] is None  # no BMR to compare with

    async with sessionmaker.begin() as session:
        await BodyMetricRepository(session).put(date(2026, 10, 10), Decimal("80"))
    profile = await _ok(await api.get(f"{BASE}/profile"))
    assert (profile["bmr_kcal"], profile["weight_kg"], profile["weight_date"]) == (
        1755.0,
        80.0,
        "2026-10-10",
    )
    assert profile["kcal_target"] == 1500  # accepted as entered
    assert profile["warning"] is not None
    assert "below the estimated basal metabolic rate" in profile["warning"]

    updated = await _ok(await api.put(f"{BASE}/profile", json=FIXTURE["profile"]))
    assert (updated["kcal_target"], updated["warning"]) == (2600, None)
    assert updated["updated_at"] == "2026-10-14T20:00:00Z"

    invalid = {**FIXTURE["profile"], "height_cm": 20}
    assert (await api.put(f"{BASE}/profile", json=invalid)).status_code == 422


async def test_nutrition_requires_api_key(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        for method, path in (
            ("GET", "/foods"),
            ("GET", "/summary"),
            ("PUT", f"/log/{uuid.uuid4()}"),
            ("GET", "/profile"),
        ):
            response = await client.request(method, BASE + path)
            assert response.status_code == 401, (method, path)
