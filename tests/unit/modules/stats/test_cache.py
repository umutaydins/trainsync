"""ADR 0038: Redis being down costs only speed."""

from typing import Any

from redis.exceptions import ConnectionError as RedisConnectionError

from tests.conftest import make_settings
from trainsync.modules.stats import cache
from trainsync.modules.stats.cache import StatsCache, cache_key


class DownRedis:
    async def get(self, key: str) -> Any:
        raise RedisConnectionError("down")

    async def set(self, key: str, value: str, ex: int) -> Any:
        raise RedisConnectionError("down")


class EmptyRedis(DownRedis):
    async def get(self, key: str) -> Any:
        return None


async def _version(session: object, user_id: int) -> int:
    return 7


async def test_a_redis_outage_computes_instead(monkeypatch: Any) -> None:
    monkeypatch.setattr(cache, "data_version", _version)
    settings = make_settings()
    calls: list[int] = []

    async def compute() -> str:
        calls.append(1)
        return '{"ok": true}'

    for redis in (DownRedis(), EmptyRedis()):
        stats = StatsCache(redis, settings)  # type: ignore[arg-type]
        assert await stats.get_or_compute(None, 1, "summary", {}, compute) == '{"ok": true}'  # type: ignore[arg-type]
    assert len(calls) == 2


def test_the_key_names_the_user_version_and_parameters() -> None:
    key = cache_key(5, 12, "summary", {"period": "all", "b": 1})
    assert key.startswith("stats:5:12:summary:")
    assert key == cache_key(5, 12, "summary", {"b": 1, "period": "all"})
    assert key != cache_key(5, 13, "summary", {"b": 1, "period": "all"})
    assert StatsCache(EmptyRedis(), make_settings()).worth_it(180)  # type: ignore[arg-type]
    assert not StatsCache(EmptyRedis(), make_settings()).worth_it(179)  # type: ignore[arg-type]
