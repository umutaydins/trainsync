"""`retry_webhooks` cron (every 5 minutes): the safety net for webhook events (ADR 0008).

- `failed` events with attempts left are re-enqueued once their backoff has passed
  (2, 4, 8 … minutes after the last attempt, capped at 6 h). After 8 attempts they stay `failed`:
  those are the dead letters, counted in sync status.
- `pending` events older than 10 minutes without a live arq job are re-enqueued. Their enqueue
  was lost, e.g. Redis was down or the API died between the INSERT and the enqueue.
- `processing` events claimed more than 10 minutes ago belong to a dead worker. They become
  `failed` and follow the normal backoff.
"""

from datetime import datetime, timedelta
from typing import Any

from arq import cron
from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.logging import get_logger
from trainsync.db.models import WebhookEvent, WebhookStatus
from trainsync.db.repositories.webhook_events import WebhookEventRepository, next_retry_at
from trainsync.sync.context import job_log_context, worker_context
from trainsync.sync.queue import webhook_job_id

log = get_logger(__name__)

STALE_AFTER = timedelta(minutes=10)
BATCH_SIZE = 200
CRON_MINUTES = set(range(0, 60, 5))
_LIVE = (JobStatus.queued, JobStatus.deferred, JobStatus.in_progress)


def retry_job_id(event_id: int, attempts: int) -> str:
    return f"{webhook_job_id(event_id)}:{attempts}"


async def retry_webhooks_once(
    sessionmaker: async_sessionmaker[AsyncSession], pool: ArqRedis, now: datetime
) -> dict[str, int]:
    """One sweep; returns counts per action (for logs and tests)."""
    counts = {"retried": 0, "recovered": 0, "released": 0}
    async with sessionmaker() as session:
        candidates = await WebhookEventRepository(session).retry_candidates(
            now, stale_after=STALE_AFTER, limit=BATCH_SIZE
        )
    for event in candidates:
        if event.status == WebhookStatus.PROCESSING:
            async with sessionmaker.begin() as session:
                if await WebhookEventRepository(session).release_stuck(
                    event.id, event.last_attempt_at
                ):
                    counts["released"] += 1
            continue
        if event.status == WebhookStatus.FAILED:
            if next_retry_at(event) > now:
                continue
            if await _enqueue(pool, event):
                counts["retried"] += 1
        elif not await _has_live_job(pool, event) and await _enqueue(pool, event):
            counts["recovered"] += 1
    if any(counts.values()):
        log.info("webhook_retry_sweep", **counts)
    return counts


async def _enqueue(pool: ArqRedis, event: WebhookEvent) -> bool:
    job = await pool.enqueue_job(
        "process_webhook_event", event.id, _job_id=retry_job_id(event.id, event.attempts)
    )
    return job is not None


async def _has_live_job(pool: ArqRedis, event: WebhookEvent) -> bool:
    """The intake job, or a retry job for this or the previous attempt (a deferred retry keeps
    its id while the claim already bumped `attempts`)."""
    job_ids = {webhook_job_id(event.id)} | {
        retry_job_id(event.id, n) for n in (event.attempts, event.attempts - 1) if n >= 0
    }
    for job_id in job_ids:
        if await Job(job_id, pool).status() in _LIVE:
            return True
    return False


async def retry_webhooks(ctx: dict[str, Any]) -> dict[str, int]:
    with job_log_context(ctx, "retry_webhooks"):
        wc = worker_context(ctx)
        return await retry_webhooks_once(wc.sessionmaker, wc.redis, wc.clock())


retry_webhooks_cron = cron(
    retry_webhooks, name="retry_webhooks", minute=CRON_MINUTES, run_at_startup=True
)
