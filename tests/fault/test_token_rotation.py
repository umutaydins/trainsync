"""Failure mode: expired / rotated tokens → proactive refresh, 401 retry, per-athlete lock.

Ten concurrent callers, each with its own TokenManager and StravaClient (as separate worker
processes would have), share Redis and Postgres. fake_strava rotates the refresh token on every
refresh, so a second refresh with a stale token would fail. Exactly one refresh must happen.
"""

import asyncio
from datetime import timedelta
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.clock import FakeClock
from fake_strava.state import FakeStravaState
from tests.conftest import FAKE_STRAVA_BASE_URL
from tests.fault.helpers import GET_ACTIVITY, TOKEN, fake_calls
from tests.support.factories import create_athlete
from trainsync.core.crypto import TokenCipher
from trainsync.core.settings import Settings
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.strava.token_repository import SqlTokenStore, Tokens
from trainsync.modules.strava.tokens import RedisRefreshLock, TokenManager

CALLERS = 10


async def _poll_sleep(_: float) -> None:
    await asyncio.sleep(0.005)


def _callers(
    http: httpx.AsyncClient,
    settings: Settings,
    store: SqlTokenStore,
    redis: Redis,
    fake_clock: FakeClock,
) -> list[StravaClient]:
    settings = settings.model_copy(
        update={
            "strava_api_base_url": f"{FAKE_STRAVA_BASE_URL}/api/v3",
            "strava_oauth_base_url": f"{FAKE_STRAVA_BASE_URL}/oauth",
        }
    )
    clients = []
    for _ in range(CALLERS):
        client = StravaClient(http, settings, clock=fake_clock.now)
        manager = TokenManager(
            store, RedisRefreshLock(redis), client, clock=fake_clock.now, sleep=_poll_sleep
        )
        clients.append(client.with_token_provider(manager))
    return clients


async def _save(store: SqlTokenStore, athlete_id: int, token: dict[str, Any], expires: Any) -> None:
    await store.save(
        athlete_id, Tokens(token["access_token"], token["refresh_token"], expires, "read")
    )


async def test_concurrent_401s_refresh_once_and_everyone_succeeds(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    fake_clock: FakeClock,
    integration_settings: Settings,
) -> None:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    store = SqlTokenStore(sessionmaker, TokenCipher.from_settings(integration_settings))
    # We believe the token is good for hours; Strava has already expired it (clock skew, revoke…).
    await _save(store, athlete_id, fake_strava_token, fake_clock.now() + timedelta(hours=5))
    await fake_strava_client.post("/_control/expire-tokens", json={})
    activity_id = next(iter(fake_strava.activities))
    clients = _callers(fake_strava_client, integration_settings, store, redis, fake_clock)

    results = await asyncio.wait_for(
        asyncio.gather(*(c.get_activity(athlete_id, activity_id) for c in clients)), timeout=20
    )
    assert {r.id for r in results} == {activity_id}
    assert fake_calls(fake_strava, TOKEN) == 2  # the initial login + exactly one refresh
    assert fake_calls(fake_strava, GET_ACTIVITY, "401") == CALLERS
    assert fake_calls(fake_strava, GET_ACTIVITY, "200") == CALLERS
    stored = await store.get(athlete_id)
    assert stored is not None
    assert stored.refresh_token != fake_strava_token["refresh_token"]  # rotation persisted
    assert not await redis.exists(RedisRefreshLock.key(athlete_id))


async def test_concurrent_proactive_refresh_happens_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    fake_clock: FakeClock,
    integration_settings: Settings,
) -> None:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    store = SqlTokenStore(sessionmaker, TokenCipher.from_settings(integration_settings))
    await _save(store, athlete_id, fake_strava_token, fake_clock.now() + timedelta(minutes=2))
    activity_id = next(iter(fake_strava.activities))
    clients = _callers(fake_strava_client, integration_settings, store, redis, fake_clock)

    await asyncio.wait_for(
        asyncio.gather(*(c.get_activity(athlete_id, activity_id) for c in clients)), timeout=20
    )
    assert fake_calls(fake_strava, TOKEN) == 2
    assert fake_calls(fake_strava, GET_ACTIVITY, "401") == 0

    # The rotated refresh token works for the next refresh, much later.
    fake_clock.advance(timedelta(hours=7))
    await clients[0].get_activity(athlete_id, activity_id)
    assert fake_calls(fake_strava, TOKEN) == 3
