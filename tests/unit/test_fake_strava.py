from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from fake_strava.app import create_app
from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.seed import DEFAULT_ATHLETE_ID, SEED_END, seed_activities
from fake_strava.state import FakeStravaState
from tests.conftest import FAKE_STRAVA_BASE_URL, fake_strava_login

ACTIVITIES = "/api/v3/athlete/activities"


def bearer(token: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {token['access_token']}"}


# ---------------------------------------------------------------- oauth


async def test_authorize_redirects_with_code_state_and_scope(
    fake_strava_client: httpx.AsyncClient,
) -> None:
    response = await fake_strava_client.get(
        "/oauth/authorize",
        params={
            "client_id": "1",
            "redirect_uri": "http://localhost:8000/auth/strava/callback?x=1",
            "response_type": "code",
            "scope": "read,activity:read_all",
            "state": "abc",
            "approval_prompt": "auto",
        },
    )
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    assert location.path == "/auth/strava/callback"
    query = parse_qs(location.query)
    assert query["x"] == ["1"]
    assert query["state"] == ["abc"]
    assert query["scope"] == ["read,activity:read_all"]
    assert query["code"][0]


async def test_code_token_refresh_flow_rotates_refresh_token(
    fake_strava_client: httpx.AsyncClient,
) -> None:
    token = await fake_strava_login(fake_strava_client)
    assert token["token_type"] == "Bearer"
    assert token["athlete"]["id"] == DEFAULT_ATHLETE_ID
    assert token["expires_in"] == 21600

    me = await fake_strava_client.get("/api/v3/athlete", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["id"] == DEFAULT_ATHLETE_ID

    refresh_form = {
        "client_id": "1234",
        "client_secret": "x",
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }
    refreshed = await fake_strava_client.post("/oauth/token", data=refresh_form)
    assert refreshed.status_code == 200
    new = refreshed.json()
    assert "athlete" not in new
    assert new["refresh_token"] != token["refresh_token"]
    assert new["access_token"] != token["access_token"]
    me = await fake_strava_client.get("/api/v3/athlete", headers=bearer(new))
    assert me.status_code == 200

    # The old refresh token is invalid after rotation.
    reused = await fake_strava_client.post("/oauth/token", data=refresh_form)
    assert reused.status_code == 400


async def test_code_is_single_use(fake_strava_client: httpx.AsyncClient) -> None:
    authorize = await fake_strava_client.get(
        "/oauth/authorize", params={"redirect_uri": "http://x/cb", "scope": "read"}
    )
    code = parse_qs(urlsplit(authorize.headers["location"]).query)["code"][0]
    form = {"grant_type": "authorization_code", "code": code}
    assert (await fake_strava_client.post("/oauth/token", data=form)).status_code == 200
    assert (await fake_strava_client.post("/oauth/token", data=form)).status_code == 400


async def test_client_credentials_checked_when_configured(fake_clock: FakeClock) -> None:
    app = create_app(FakeStravaConfig(client_id="1234", client_secret="right"), fake_clock)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=FAKE_STRAVA_BASE_URL
    ) as client:
        authorize = await client.get("/oauth/authorize", params={"redirect_uri": "http://x/cb"})
        code = parse_qs(urlsplit(authorize.headers["location"]).query)["code"][0]
        wrong = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": "1234",
                "client_secret": "wrong",
            },
        )
    assert wrong.status_code == 400


# ---------------------------------------------------------------- auth


async def test_unknown_or_missing_bearer_is_401(fake_strava_client: httpx.AsyncClient) -> None:
    unknown = await fake_strava_client.get(
        "/api/v3/athlete", headers={"Authorization": "Bearer nope"}
    )
    assert unknown.status_code == 401
    assert unknown.json()["message"] == "Authorization Error"
    missing = await fake_strava_client.get("/api/v3/athlete")
    assert missing.status_code == 401


async def test_token_expires_after_ttl(
    fake_strava_client: httpx.AsyncClient, fake_clock: FakeClock
) -> None:
    token = await fake_strava_login(fake_strava_client)
    assert token["expires_at"] == int(fake_clock.now().timestamp()) + 21600
    fake_clock.advance(timedelta(seconds=21599))
    assert (
        await fake_strava_client.get("/api/v3/athlete", headers=bearer(token))
    ).status_code == 200
    fake_clock.advance(timedelta(seconds=1))
    assert (
        await fake_strava_client.get("/api/v3/athlete", headers=bearer(token))
    ).status_code == 401


async def test_control_expire_tokens(fake_strava_client: httpx.AsyncClient) -> None:
    token = await fake_strava_login(fake_strava_client)
    response = await fake_strava_client.post("/_control/expire-tokens")
    assert response.json() == {"expired": 1}
    assert (
        await fake_strava_client.get("/api/v3/athlete", headers=bearer(token))
    ).status_code == 401


# ---------------------------------------------------------------- activities


async def test_pagination_200_100_then_empty(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    pages = []
    for page in (1, 2, 3):
        response = await fake_strava_client.get(
            ACTIVITIES, params={"page": page, "per_page": 200}, headers=bearer(fake_strava_token)
        )
        assert response.status_code == 200
        pages.append(response.json())
    assert [len(p) for p in pages] == [200, 100, 0]

    starts = [a["start_date"] for a in pages[0] + pages[1]]
    assert starts == sorted(starts, reverse=True)
    assert len({a["id"] for a in pages[0] + pages[1]}) == 300


async def test_per_page_is_capped_at_200(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    response = await fake_strava_client.get(
        ACTIVITIES, params={"per_page": 500}, headers=bearer(fake_strava_token)
    )
    assert len(response.json()) == 200


async def test_before_and_after_filters(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    everything = (
        await fake_strava_client.get(
            ACTIVITIES, params={"per_page": 200}, headers=bearer(fake_strava_token)
        )
    ).json()
    pivot = everything[50]
    pivot_ts = int(datetime.fromisoformat(pivot["start_date"]).timestamp())

    before = (
        await fake_strava_client.get(
            ACTIVITIES,
            params={"before": pivot_ts, "per_page": 200},
            headers=bearer(fake_strava_token),
        )
    ).json()
    assert before[0]["id"] == everything[51]["id"]
    assert all(datetime.fromisoformat(a["start_date"]).timestamp() < pivot_ts for a in before)

    after = (
        await fake_strava_client.get(
            ACTIVITIES,
            params={"after": pivot_ts, "per_page": 200},
            headers=bearer(fake_strava_token),
        )
    ).json()
    assert [a["id"] for a in after] == [a["id"] for a in everything[:50]]

    window = (
        await fake_strava_client.get(
            ACTIVITIES,
            params={
                "after": pivot_ts,
                "before": int(datetime.fromisoformat(everything[10]["start_date"]).timestamp()),
                "per_page": 200,
            },
            headers=bearer(fake_strava_token),
        )
    ).json()
    assert [a["id"] for a in window] == [a["id"] for a in everything[11:50]]


async def test_activity_json_shape(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    items = (
        await fake_strava_client.get(
            ACTIVITIES, params={"per_page": 200}, headers=bearer(fake_strava_token)
        )
    ).json()
    first = items[0]
    assert first["start_date"].endswith("Z")
    assert set(first) >= {
        "id",
        "name",
        "sport_type",
        "start_date",
        "distance",
        "moving_time",
        "elapsed_time",
        "total_elevation_gain",
    }
    assert isinstance(first["distance"], float)
    # Some seeded activities have no heart rate, like real ones without a strap.
    assert any("average_heartrate" not in a for a in items)
    assert any("average_heartrate" in a for a in items)


async def test_get_activity_and_404(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    listed = (await fake_strava_client.get(ACTIVITIES, headers=bearer(fake_strava_token))).json()[0]
    one = await fake_strava_client.get(
        f"/api/v3/activities/{listed['id']}", headers=bearer(fake_strava_token)
    )
    assert one.status_code == 200
    assert one.json() == listed

    missing = await fake_strava_client.get(
        "/api/v3/activities/1", headers=bearer(fake_strava_token)
    )
    assert missing.status_code == 404
    assert missing.json()["message"] == "Record Not Found"


async def test_seed_is_deterministic() -> None:
    first = [a.to_json() for a in seed_activities(DEFAULT_ATHLETE_ID, 300, rng_seed=7)]
    again = [a.to_json() for a in seed_activities(DEFAULT_ATHLETE_ID, 300, rng_seed=7)]
    other = [a.to_json() for a in seed_activities(DEFAULT_ATHLETE_ID, 300, rng_seed=8)]
    assert first == again
    assert first != other
    assert all(datetime.fromisoformat(a["start_date"]) < SEED_END for a in first)


async def test_two_apps_with_same_seed_serve_identical_activities(fake_clock: FakeClock) -> None:
    results = []
    for _ in range(2):
        app = create_app(FakeStravaConfig(rng_seed=3), fake_clock)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=FAKE_STRAVA_BASE_URL
        ) as client:
            token = await fake_strava_login(client)
            response = await client.get(ACTIVITIES, params={"per_page": 200}, headers=bearer(token))
            results.append(response.json())
    assert results[0] == results[1]


async def test_multiple_athletes_have_separate_activities(fake_clock: FakeClock) -> None:
    state = FakeStravaState(FakeStravaConfig(athletes=2, seed_activities=5), fake_clock)
    owners = {a.athlete_id for a in state.activities.values()}
    assert owners == {DEFAULT_ATHLETE_ID, DEFAULT_ATHLETE_ID + 1}
    assert len(state.activities) == 10


# ---------------------------------------------------------------- rate limits


async def test_rate_limit_headers_present_and_usage_increments(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    usages = []
    for _ in range(3):
        response = await fake_strava_client.get(
            "/api/v3/athlete", headers=bearer(fake_strava_token)
        )
        assert response.headers["X-RateLimit-Limit"] == "200,2000"
        assert response.headers["X-ReadRateLimit-Limit"] == "200,2000"
        assert response.headers["X-ReadRateLimit-Usage"] == response.headers["X-RateLimit-Usage"]
        usages.append(response.headers["X-RateLimit-Usage"])
    assert usages == ["1,1", "2,2", "3,3"]


async def test_429_until_next_quarter_hour(
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    fake_clock: FakeClock,
) -> None:
    fake_clock.set(datetime(2026, 10, 17, 12, 7, tzinfo=UTC))
    await fake_strava_client.post("/_control/config", json={"rate_limit_15min": 3})
    statuses = [
        (
            await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
        ).status_code
        for _ in range(5)
    ]
    assert statuses == [200, 200, 200, 429, 429]

    fake_clock.set(datetime(2026, 10, 17, 12, 14, 59, tzinfo=UTC))
    limited = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert limited.status_code == 429
    assert limited.headers["X-RateLimit-Usage"] == "3,3"
    assert limited.json()["message"] == "Rate Limit Exceeded"

    fake_clock.set(datetime(2026, 10, 17, 12, 15, tzinfo=UTC))
    reset = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert reset.status_code == 200
    assert reset.headers["X-RateLimit-Usage"] == "1,4"


async def test_daily_limit_resets_at_midnight_utc(
    fake_strava_client: httpx.AsyncClient, fake_clock: FakeClock
) -> None:
    await fake_strava_client.post("/_control/config", json={"rate_limit_daily": 2})
    fake_clock.set(datetime(2026, 10, 17, 23, 40, tzinfo=UTC))
    fake_strava_token = await fake_strava_login(fake_strava_client)
    for _ in range(2):
        await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    fake_clock.set(datetime(2026, 10, 17, 23, 50, tzinfo=UTC))  # new 15-min window, same day
    blocked = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert blocked.status_code == 429
    fake_clock.set(datetime(2026, 10, 18, 0, 0, tzinfo=UTC))
    ok = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert ok.status_code == 200
    assert ok.headers["X-RateLimit-Usage"] == "1,1"


async def test_read_limit_can_differ(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    await fake_strava_client.post("/_control/config", json={"read_rate_limit_15min": 1})
    first = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert first.headers["X-ReadRateLimit-Limit"] == "1,2000"
    second = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert second.status_code == 429


# ---------------------------------------------------------------- errors and latency


@pytest.mark.parametrize(
    ("error_rate", "expect_errors"), [(1.0, True), (0.0, False)], ids=["always", "never"]
)
async def test_error_rate(
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    error_rate: float,
    expect_errors: bool,
) -> None:
    await fake_strava_client.post("/_control/config", json={"error_rate": error_rate})
    statuses = {
        (await fake_strava_client.get(ACTIVITIES, headers=bearer(fake_strava_token))).status_code
        for _ in range(50)
    }
    if expect_errors:
        assert statuses <= {500, 502, 503}
        assert len(statuses) > 1
    else:
        assert statuses == {200}


async def test_error_responses_carry_rate_limit_headers(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    await fake_strava_client.post("/_control/config", json={"error_rate": 1.0})
    response = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert response.status_code >= 500
    assert response.headers["X-RateLimit-Usage"] == "1,1"


async def test_latency_is_applied(
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("fake_strava.app.asyncio.sleep", fake_sleep)
    await fake_strava_client.post("/_control/config", json={"latency_ms": 250})
    await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert slept == [0.25]


async def test_invalid_config_rejected(fake_strava_client: httpx.AsyncClient) -> None:
    response = await fake_strava_client.post("/_control/config", json={"error_rate": 2})
    assert response.status_code == 422


# ---------------------------------------------------------------- control


async def test_control_activity_create_update_delete(
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    fake_strava: FakeStravaState,
) -> None:
    created = (
        await fake_strava_client.post(
            "/_control/activities",
            json={"action": "create", "fields": {"name": "Lunch Run", "distance": 8000.0}},
        )
    ).json()
    activity_id = created["id"]
    assert created["athlete_id"] == DEFAULT_ATHLETE_ID
    newest = (await fake_strava_client.get(ACTIVITIES, headers=bearer(fake_strava_token))).json()[0]
    assert newest["id"] == activity_id
    assert newest["name"] == "Lunch Run"

    await fake_strava_client.post(
        "/_control/activities",
        json={"action": "update", "id": activity_id, "fields": {"name": "Renamed"}},
    )
    got = await fake_strava_client.get(
        f"/api/v3/activities/{activity_id}", headers=bearer(fake_strava_token)
    )
    assert got.json()["name"] == "Renamed"

    await fake_strava_client.post(
        "/_control/activities", json={"action": "delete", "id": activity_id}
    )
    gone = await fake_strava_client.get(
        f"/api/v3/activities/{activity_id}", headers=bearer(fake_strava_token)
    )
    assert gone.status_code == 404
    assert [c.action for c in fake_strava.changes] == ["create", "update", "delete"]


async def test_control_activity_errors(fake_strava_client: httpx.AsyncClient) -> None:
    unknown = await fake_strava_client.post(
        "/_control/activities", json={"action": "update", "id": 1, "fields": {}}
    )
    assert unknown.status_code == 404
    bad_field = await fake_strava_client.post(
        "/_control/activities", json={"action": "create", "fields": {"nope": 1}}
    )
    assert bad_field.status_code == 422


async def test_stats_count_by_endpoint_template_and_status(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    await fake_strava_client.get("/api/v3/activities/1", headers=bearer(fake_strava_token))
    await fake_strava_client.get("/api/v3/activities/2", headers=bearer(fake_strava_token))
    await fake_strava_client.get(ACTIVITIES, headers=bearer(fake_strava_token))
    stats = (await fake_strava_client.get("/_control/stats")).json()
    assert stats["requests"]["GET /api/v3/activities/{activity_id}"] == {"404": 2}
    assert stats["requests"]["GET /api/v3/athlete/activities"] == {"200": 1}
    assert stats["requests"]["POST /oauth/token"] == {"200": 1}
    assert stats["requests"]["GET /oauth/authorize"] == {"302": 1}
    assert stats["rate_limit"] == {"short_usage": 3, "daily_usage": 3}
    assert stats["total"] == 5


async def test_reset_restores_seed_and_clears_tokens(
    fake_strava_client: httpx.AsyncClient, fake_strava_token: dict[str, Any]
) -> None:
    await fake_strava_client.post("/_control/activities", json={"action": "create"})
    response = await fake_strava_client.post("/_control/reset")
    assert response.json() == {"status": "reset", "activities": 300}
    after = await fake_strava_client.get("/api/v3/athlete", headers=bearer(fake_strava_token))
    assert after.status_code == 401
    assert (await fake_strava_client.get("/_control/stats")).json()["total"] == 1


def test_fake_clock_requires_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(datetime(2026, 1, 1))
