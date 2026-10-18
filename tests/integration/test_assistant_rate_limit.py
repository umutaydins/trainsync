"""P5.7: the per-chat question limit lives in Redis (fixed one-hour windows)."""

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from tests.fault.helpers import ManualClock
from trainsync.bot.assistant import RedisRateLimiter


async def test_per_chat_hourly_limit(redis: Redis) -> None:
    clock = ManualClock(datetime(2026, 10, 18, 9, 0, 5, tzinfo=UTC))
    limiter = RedisRateLimiter(redis, limit_per_hour=20, clock=clock)

    assert [await limiter.allow(42) for _ in range(21)] == [True] * 20 + [False]
    assert await limiter.allow(43)  # other chats have their own budget

    clock.advance(timedelta(minutes=50))  # same window (09:00-10:00)
    assert not await limiter.allow(42)
    clock.advance(timedelta(minutes=10))  # 10:00:05: a new window
    assert await limiter.allow(42)

    ttls = [await redis.ttl(key) async for key in redis.scan_iter("assistant:quota:*")]
    assert ttls
    assert all(0 < ttl <= 3600 for ttl in ttls)  # keys clean themselves up
