import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from tests.support.strava import API, OAUTH, Recorder, StubTokens, activity_json, make_client
from trainsync.core.settings import Settings
from trainsync.integrations.strava.budget import Allowance
from trainsync.integrations.strava.errors import (
    RateLimited,
    StravaAuthError,
    StravaNotFound,
    StravaRequestError,
    StravaUnavailable,
)

RL_HEADERS = {"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "10,20"}


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("slow"),
        httpx.Response(500),
        httpx.Response(502),
        httpx.Response(503),
        httpx.Response(504),
    ],
    ids=["connect", "read-timeout", "connect-timeout", "500", "502", "503", "504"],
)
@respx.mock
async def test_retries_transient_failures_then_succeeds(
    failure: Exception | httpx.Response, http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/activities/7").mock(
        side_effect=[failure, httpx.Response(200, json=activity_json(7))]
    )
    recorder = Recorder()
    activity = await make_client(http, settings, recorder=recorder).get_activity(1, 7)
    assert activity.id == 7
    assert route.call_count == 2
    assert len(recorder.sleeps) == 1
    assert 0 <= recorder.sleeps[0] <= 0.5


@pytest.mark.parametrize("status", [400, 403, 404, 422])
@respx.mock
async def test_does_not_retry_client_errors(
    status: int, http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(status))
    expected = StravaNotFound if status == 404 else StravaRequestError
    with pytest.raises(expected):
        await make_client(http, settings).get_activity(1, 7)
    assert route.call_count == 1


@respx.mock
async def test_gives_up_after_max_attempts(http: httpx.AsyncClient, settings: Settings) -> None:
    route = respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(503))
    recorder = Recorder()
    with pytest.raises(StravaUnavailable):
        await make_client(http, settings, recorder=recorder).get_activity(1, 7)
    assert route.call_count == 4
    assert len(recorder.sleeps) == 3
    for attempt, delay in enumerate(recorder.sleeps):
        assert 0 <= delay <= 0.5 * 2**attempt


@respx.mock
async def test_429_raises_rate_limited_without_retry(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/athlete/activities").mock(
        return_value=httpx.Response(429, headers=RL_HEADERS)
    )
    recorder = Recorder()
    with pytest.raises(RateLimited) as exc_info:
        await make_client(http, settings, recorder=recorder).list_activities(1)
    assert exc_info.value.reset_at == datetime(2026, 10, 17, 12, 15, tzinfo=UTC)
    assert route.call_count == 1
    assert recorder.sleeps == []
    assert len(recorder.snapshots) == 1  # headers of the 429 are still recorded


@respx.mock
async def test_rate_limit_snapshot_handed_to_callback(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    respx.get(f"{API}/athlete").mock(
        return_value=httpx.Response(200, json={"id": 5, "firstname": "A"}, headers=RL_HEADERS)
    )
    recorder = Recorder()
    athlete = await make_client(http, settings, recorder=recorder).get_athlete(1)
    assert athlete.id == 5
    assert recorder.snapshots[0].short_ratio == 0.05


@respx.mock
async def test_list_activities_params_and_models(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    no_hr = activity_json(2)
    del no_hr["average_heartrate"]
    route = respx.get(f"{API}/athlete/activities").mock(
        return_value=httpx.Response(200, json=[activity_json(1), no_hr])
    )
    tokens = StubTokens(token="tok-xyz")
    items = await make_client(http, settings, tokens=tokens).list_activities(
        1, before=1_700_000_000, page=1, per_page=200
    )
    request = route.calls.last.request
    assert dict(request.url.params) == {"page": "1", "per_page": "200", "before": "1700000000"}
    assert request.headers["authorization"] == "Bearer tok-xyz"
    assert items[0].average_heartrate == 151.2
    assert items[1].average_heartrate is None
    assert items[0].start_date == datetime(2026, 10, 1, 6, 30, tzinfo=UTC)
    assert items[0].distance == 10012.5
    assert items[0].raw()["kudos_count"] == 3


@respx.mock
async def test_exchange_code_and_refresh(http: httpx.AsyncClient, settings: Settings) -> None:
    body = {
        "token_type": "Bearer",
        "access_token": "a",
        "refresh_token": "r",
        "expires_at": 1_800_000_000,
        "expires_in": 21600,
        "athlete": {"id": 99, "firstname": "U", "lastname": "A"},
    }
    route = respx.post(f"{OAUTH}/token").mock(return_value=httpx.Response(200, json=body))
    client = make_client(http, settings)
    token = await client.exchange_code("the-code")
    assert token.athlete is not None
    assert token.athlete.id == 99
    assert token.expires_at == datetime.fromtimestamp(1_800_000_000, tz=UTC)
    form = dict(httpx.QueryParams(route.calls.last.request.content.decode()))
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "the-code"
    assert form["client_secret"] == "client-secret-value"
    assert "a" not in repr(token).split("(")[0]
    assert "refresh_token" not in repr(token)

    await client.refresh("r")
    form = dict(httpx.QueryParams(route.calls.last.request.content.decode()))
    assert form == form | {"grant_type": "refresh_token", "refresh_token": "r"}


@respx.mock
async def test_token_endpoint_rejection_is_auth_error(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    respx.post(f"{OAUTH}/token").mock(return_value=httpx.Response(400))
    with pytest.raises(StravaAuthError):
        await make_client(http, settings).refresh("old")


# Outbound clients for other services (Phase 5), named one by one; they must not touch Strava.
NON_STRAVA_HTTP_CLIENTS = {
    "core/http.py",
    "integrations/telegram/client.py",
    "modules/chat/read_api.py",
    "modules/notifications/tasks.py",
    "modules/notifications/checkin.py",
    "modules/notifications/coach.py",
    "integrations/openfoodfacts/client.py",
}


def test_only_strava_package_imports_httpx() -> None:
    src = Path(__file__).resolve().parents[4] / "src" / "trainsync"
    pattern = re.compile(r"^\s*(import httpx|from httpx\b)", re.MULTILINE)
    importers = {
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if pattern.search(path.read_text()) and path.parent.name != "strava"
    }
    assert importers - NON_STRAVA_HTTP_CLIENTS == set()
    strava_access = re.compile(r"strava\.com|strava_(api|oauth)_|trainsync\.integrations\.strava\b")
    for name in NON_STRAVA_HTTP_CLIENTS:
        assert not strava_access.search((src / name).read_text()), name


@respx.mock
async def test_401_refreshes_once_and_retries_once(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/activities/7").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=activity_json(7))]
    )
    tokens = StubTokens()
    await make_client(http, settings, tokens=tokens).get_activity(1, 7)
    assert tokens.refresh_calls == 1
    assert route.call_count == 2
    assert route.calls[1].request.headers["authorization"] == "Bearer access-2"


@respx.mock
async def test_second_401_is_auth_error(http: httpx.AsyncClient, settings: Settings) -> None:
    route = respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(401))
    tokens = StubTokens()
    with pytest.raises(StravaAuthError):
        await make_client(http, settings, tokens=tokens).get_activity(1, 7)
    assert route.call_count == 2
    assert tokens.refresh_calls == 1


@respx.mock
async def test_budget_denial_raises_without_calling_strava(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(200))
    resume = datetime(2026, 10, 17, 12, 15, tzinfo=UTC)
    recorder = Recorder(deny=Allowance(False, resume))
    with pytest.raises(RateLimited) as exc_info:
        await make_client(http, settings, recorder=recorder).get_activity(1, 7, priority="low")
    assert exc_info.value.reset_at == resume
    assert route.call_count == 0


@respx.mock
async def test_429_blocks_the_budget_until_window_reset(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(429, headers=RL_HEADERS))
    recorder = Recorder()
    with pytest.raises(RateLimited):
        await make_client(http, settings, recorder=recorder).get_activity(1, 7)
    assert recorder.blocked == [datetime(2026, 10, 17, 12, 15, tzinfo=UTC)]


@respx.mock
async def test_429_with_daily_budget_exhausted_waits_for_midnight(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    headers = {"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "150,2000"}
    respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(429, headers=headers))
    recorder = Recorder()
    with pytest.raises(RateLimited) as exc_info:
        await make_client(http, settings, recorder=recorder).get_activity(1, 7)
    assert exc_info.value.reset_at == datetime(2026, 10, 18, tzinfo=UTC)
    assert recorder.blocked == [datetime(2026, 10, 18, tzinfo=UTC)]


@respx.mock
async def test_oauth_calls_skip_the_budget(http: httpx.AsyncClient, settings: Settings) -> None:
    body = {"access_token": "a", "refresh_token": "r", "expires_at": 1_800_000_000}
    respx.post(f"{OAUTH}/token").mock(return_value=httpx.Response(200, json=body))
    recorder = Recorder(deny=Allowance(False, datetime(2026, 10, 18, tzinfo=UTC)))
    token = await make_client(http, settings, recorder=recorder).refresh("r")
    assert token.access_token == "a"
