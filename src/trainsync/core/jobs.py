"""Enqueueing background jobs (arq). Job ids make repeated enqueues no-ops."""

from typing import Protocol

from arq.connections import ArqRedis, RedisSettings

from trainsync.core.settings import Settings


class JobQueue(Protocol):
    async def enqueue_backfill(self, athlete_id: int) -> bool: ...

    async def enqueue_webhook_event(self, event_id: int) -> bool: ...


class CoachEvents(Protocol):
    """Workout events the worker's coach reacts to (P6.11, ADR 0030)."""

    async def coach_event(self, job: str, object_id: int) -> None: ...


COACH_EVENT_JOBS = frozenset(
    {"coach_workout_started", "coach_set_logged", "coach_workout_finished"}
)


def backfill_job_id(athlete_id: int) -> str:
    return f"backfill:{athlete_id}"


def webhook_job_id(event_id: int) -> str:
    return f"webhook:{event_id}"


def notify_job_id(strava_activity_id: int) -> str:
    return f"notify:{strava_activity_id}"


async def enqueue_new_activity_notification(pool: ArqRedis, strava_activity_id: int) -> bool:
    """`False` when this activity's notification job is already queued (or recently done)."""
    job = await pool.enqueue_job(
        "notify_new_activity", strava_activity_id, _job_id=notify_job_id(strava_activity_id)
    )
    return job is not None


class ArqJobQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self.pool = pool

    async def enqueue_backfill(self, athlete_id: int) -> bool:
        """`False` when a backfill job for this athlete is already queued or running."""
        job = await self.pool.enqueue_job(
            "backfill", athlete_id, _job_id=backfill_job_id(athlete_id)
        )
        return job is not None

    async def enqueue_webhook_event(self, event_id: int) -> bool:
        """`False` when a job for this event is already queued or running."""
        job = await self.pool.enqueue_job(
            "process_webhook_event", event_id, _job_id=webhook_job_id(event_id)
        )
        return job is not None

    async def coach_event(self, job: str, object_id: int) -> None:
        """Queue a coach job once per object (the job id dedupes; the worker's `notifications`
        claim dedupes the message itself)."""
        if job not in COACH_EVENT_JOBS:
            raise ValueError(f"unknown coach job {job!r}")
        await self.pool.enqueue_job(job, object_id, _job_id=f"{job}:{object_id}")


def redis_settings(settings: Settings) -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


def create_arq_redis(settings: Settings) -> ArqRedis:
    """Connects lazily (unlike `arq.create_pool`), so the API starts even when Redis is down
    and `/health/ready` can report it."""
    client: ArqRedis = ArqRedis.from_url(
        settings.redis_url, socket_connect_timeout=2, socket_timeout=5
    )
    return client
