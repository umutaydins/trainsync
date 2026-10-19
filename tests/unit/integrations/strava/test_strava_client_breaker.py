from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from tests.support.strava import API, NOW, Recorder, StubTokens, activity_json, make_client
from trainsync.core.settings import Settings
from trainsync.integrations.strava.breaker import BreakerState
from trainsync.integrations.strava.budget import Allowance
from trainsync.integrations.strava.errors import (
    CircuitOpen,
    RateLimited,
    StravaError,
    StravaUnavailable,
)

RL_HEADERS = {"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "10,20"}


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@respx.mock
async def test_exhausted_retries_open_the_circuit_and_stop_calls(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(503))
    client = make_client(http, settings)
    for _ in range(settings.strava_breaker_failure_threshold):
        with pytest.raises(StravaUnavailable):
            await client.get_activity(1, 7)
    assert client.breaker_state is BreakerState.OPEN
    calls = route.call_count
    assert calls == 4 * settings.strava_breaker_failure_threshold  # 4 attempts per logical call

    with pytest.raises(CircuitOpen) as exc_info:
        await client.get_activity(1, 7)
    assert route.call_count == calls  # failed fast, no request
    assert (exc_info.value.retry_at - NOW).total_seconds() == settings.strava_breaker_cooldown_s


@respx.mock
async def test_timeouts_open_the_circuit(http: httpx.AsyncClient, settings: Settings) -> None:
    respx.get(f"{API}/activities/7").mock(side_effect=httpx.ReadTimeout("slow"))
    client = make_client(http, settings)
    for _ in range(settings.strava_breaker_failure_threshold):
        with pytest.raises(StravaUnavailable):
            await client.get_activity(1, 7)
    assert client.breaker_state is BreakerState.OPEN


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
@respx.mock
async def test_client_errors_and_429_never_open_the_circuit(
    status: int, http: httpx.AsyncClient, settings: Settings
) -> None:
    route = respx.get(f"{API}/activities/7").mock(
        return_value=httpx.Response(status, headers=RL_HEADERS)
    )
    client = make_client(http, settings)
    for _ in range(3 * settings.strava_breaker_failure_threshold):
        with pytest.raises(StravaError) as exc_info:
            await client.get_activity(1, 7)
        assert not isinstance(exc_info.value, CircuitOpen | StravaUnavailable)
    assert client.breaker_state is BreakerState.CLOSED
    assert route.call_count >= 3 * settings.strava_breaker_failure_threshold


@respx.mock
async def test_budget_denial_does_not_touch_the_breaker(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    respx.get(f"{API}/activities/7").mock(return_value=httpx.Response(503))
    recorder = Recorder()
    client = make_client(http, settings, recorder=recorder)
    for _ in range(settings.strava_breaker_failure_threshold - 1):
        with pytest.raises(StravaUnavailable):
            await client.get_activity(1, 7)
    recorder.deny = Allowance(False, NOW)
    with pytest.raises(RateLimited):
        await client.get_activity(1, 7)
    assert client.breaker_state is BreakerState.CLOSED


@respx.mock
async def test_success_keeps_the_circuit_closed(
    http: httpx.AsyncClient, settings: Settings
) -> None:
    respx.get(f"{API}/activities/7").mock(
        side_effect=[httpx.Response(503)] * 4 * 4
        + [httpx.Response(200, json=activity_json(7))]
        + [httpx.Response(503)] * 4 * 4
    )
    client = make_client(http, settings, tokens=StubTokens())
    for _ in range(4):
        with pytest.raises(StravaUnavailable):
            await client.get_activity(1, 7)
    assert (await client.get_activity(1, 7)).id == 7
    for _ in range(4):
        with pytest.raises(StravaUnavailable):
            await client.get_activity(1, 7)
    assert client.breaker_state is BreakerState.CLOSED
