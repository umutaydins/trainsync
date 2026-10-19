"""P5.7: the per-chat question limit lives in Redis (fixed one-hour windows)."""

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from tests.fault.helpers import ManualClock
from trainsync.modules.chat.assistant import Asker, DailyQuota, RedisRateLimiter


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


async def test_daily_limit_per_user_in_their_local_day_and_the_owner_is_exempt(
    redis: Redis,
) -> None:
    """P8.5, ADR 0036: ASSISTANT_DAILY_LIMIT questions per user and local day."""
    clock = ManualClock(datetime(2026, 10, 18, 21, 30, tzinfo=UTC))  # 00:30 in Istanbul
    quota = DailyQuota(redis, limit=3, clock=clock)
    istanbul = Asker(2, "Europe/Istanbul")
    london = Asker(3, "Europe/London")
    owner = Asker(1, "UTC", unlimited=True)

    assert [await quota.allow(istanbul) for _ in range(4)] == [True, True, True, False]
    assert await quota.allow(london)  # someone else's budget
    assert all([await quota.allow(owner) for _ in range(10)])
    clock.advance(timedelta(hours=22))  # 22:30 Istanbul on 10-19: still the same local day
    assert not await quota.allow(istanbul)
    clock.advance(timedelta(hours=2))  # 00:30 on 10-20 local: a new day
    assert await quota.allow(istanbul)
