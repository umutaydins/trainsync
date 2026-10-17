"""Redis client factory (redis.asyncio)."""

from redis.asyncio import Redis

from trainsync.core.settings import Settings


def create_redis(settings: Settings) -> Redis:
    client: Redis = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=5,
        health_check_interval=30,
    )
    return client
