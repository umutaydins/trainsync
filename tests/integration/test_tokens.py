import asyncio
from datetime import timedelta

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.clock import FakeClock
from tests.conftest import FAKE_STRAVA_BASE_URL, fake_strava_login
from trainsync.core.crypto import TokenCipher
from trainsync.core.settings import Settings
from trainsync.db.models import Athlete, OAuthToken
from trainsync.db.repositories.tokens import SqlTokenStore, TokenRepository, Tokens
from trainsync.strava.client import StravaClient
from trainsync.strava.models import TokenResponse
from trainsync.strava.tokens import RedisRefreshLock, TokenManager


async def _athlete(sessionmaker: async_sessionmaker[AsyncSession], strava_id: int = 1001) -> int:
    async with sessionmaker.begin() as session:
        athlete = Athlete(strava_athlete_id=strava_id)
        session.add(athlete)
        await session.flush()
        return athlete.id


async def test_tokens_stored_as_ciphertext(
    sessionmaker: async_sessionmaker[AsyncSession], integration_settings: Settings
) -> None:
    athlete_id = await _athlete(sessionmaker)
    cipher = TokenCipher.from_settings(integration_settings)
    store = SqlTokenStore(sessionmaker, cipher)
    expires = FakeClock().now() + timedelta(hours=1)
    await store.save(athlete_id, Tokens("plain-access", "plain-refresh", expires, "read"))

    async with sessionmaker() as session:
        row = await session.scalar(select(OAuthToken))
        assert row is not None
        assert b"plain-access" not in row.access_token_enc
        assert b"plain-refresh" not in row.refresh_token_enc
        assert cipher.decrypt(row.access_token_enc) == "plain-access"
        loaded = await TokenRepository(session, cipher).get(athlete_id)
    assert loaded == Tokens("plain-access", "plain-refresh", expires, "read")

    async with sessionmaker.begin() as session:
        await TokenRepository(session, cipher).delete(athlete_id)
    assert await store.get(athlete_id) is None


async def test_concurrent_access_token_calls_refresh_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    redis: Redis,
    fake_strava_app: FastAPI,
    fake_strava_client: httpx.AsyncClient,
    fake_clock: FakeClock,
) -> None:
    """Two jobs, one expiring token: exactly one POST /oauth/token, both get the new token."""
    login = await fake_strava_login(fake_strava_client)
    athlete_id = await _athlete(sessionmaker)
    store = SqlTokenStore(sessionmaker, TokenCipher.from_settings(integration_settings))
    almost_expired = fake_clock.now() + timedelta(minutes=1)
    await store.save(
        athlete_id,
        Tokens(login["access_token"], login["refresh_token"], almost_expired, "read"),
    )

    settings = integration_settings.model_copy(
        update={"strava_oauth_base_url": f"{FAKE_STRAVA_BASE_URL}/oauth"}
    )
    client = StravaClient(fake_strava_client, settings)
    waiter_saw_lock = asyncio.Event()

    class GatedRefresher:
        """Hold the refresh until the other caller is provably waiting on the lock."""

        async def refresh(self, refresh_token: str) -> TokenResponse:
            await waiter_saw_lock.wait()
            return await client.refresh(refresh_token)

    async def poll_sleep(_: float) -> None:
        waiter_saw_lock.set()
        await asyncio.sleep(0.01)

    def make_manager() -> TokenManager:
        return TokenManager(
            store,
            RedisRefreshLock(redis),
            GatedRefresher(),
            clock=fake_clock.now,
            sleep=poll_sleep,
        )

    before = fake_strava_app.state.fake.stats_json()["requests"].get("POST /oauth/token", {})
    first, second = await asyncio.wait_for(
        asyncio.gather(
            make_manager().access_token(athlete_id), make_manager().access_token(athlete_id)
        ),
        timeout=10,
    )
    after = fake_strava_app.state.fake.stats_json()["requests"]["POST /oauth/token"]

    assert first == second != login["access_token"]
    assert sum(after.values()) - sum(before.values()) == 1
    stored = await store.get(athlete_id)
    assert stored is not None
    assert stored.access_token == first
    assert stored.refresh_token != login["refresh_token"]  # rotated token persisted
    assert not await redis.exists(RedisRefreshLock.key(athlete_id))


async def test_lock_is_only_released_by_its_owner(redis: Redis) -> None:
    lock = RedisRefreshLock(redis)
    owner = await lock.acquire(42)
    assert owner is not None
    assert await lock.acquire(42) is None
    await lock.release(42, "not-the-owner")
    assert await lock.is_held(42)
    await lock.release(42, owner)
    assert not await lock.is_held(42)
    ttl = await redis.pttl(RedisRefreshLock.key(42))
    assert ttl == -2


async def test_lock_has_ttl(redis: Redis) -> None:
    await RedisRefreshLock(redis, ttl_ms=15_000).acquire(7)
    ttl = await redis.pttl(RedisRefreshLock.key(7))
    assert 0 < ttl <= 15_000
