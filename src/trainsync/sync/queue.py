"""Enqueueing background jobs (arq). Job ids make repeated enqueues no-ops."""

from typing import Protocol

from arq.connections import ArqRedis, RedisSettings

from trainsync.core.settings import Settings


class JobQueue(Protocol):
    async def enqueue_backfill(self, athlete_id: int) -> bool: ...


def backfill_job_id(athlete_id: int) -> str:
    return f"backfill:{athlete_id}"


class ArqJobQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self.pool = pool

    async def enqueue_backfill(self, athlete_id: int) -> bool:
        """`False` when a backfill job for this athlete is already queued or running."""
        job = await self.pool.enqueue_job(
            "backfill", athlete_id, _job_id=backfill_job_id(athlete_id)
        )
        return job is not None


def redis_settings(settings: Settings) -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


def create_arq_redis(settings: Settings) -> ArqRedis:
    """Connects lazily (unlike `arq.create_pool`), so the API starts even when Redis is down
    and `/health/ready` can report it."""
    client: ArqRedis = ArqRedis.from_url(
        settings.redis_url, socket_connect_timeout=2, socket_timeout=5
    )
    return client
