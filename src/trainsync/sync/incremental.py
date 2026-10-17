"""Incremental sync: the 30-minute safety net for missed webhooks and late edits.

Fetches everything that started after `max(start_date) - 2 days` (the overlap window catches
edits to recent activities and late uploads of older ones) through the same idempotent upsert
path as the backfill. `schedule_incremental` is the cron job that fans out one job per active
athlete per 30-minute window.
"""

from datetime import datetime, timedelta
from typing import Any

from arq import cron
from arq.connections import ArqRedis
from arq.worker import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.logging import get_logger
from trainsync.db.models import Athlete, SyncKind, SyncRun, SyncStatus
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.sync_runs import SyncRunRepository, is_live
from trainsync.sync.common import (
    PER_PAGE,
    STALE_AFTER,
    SYNC_MAX_TRIES,
    RunWriter,
    SyncOutcome,
    ensure_budget,
    retry_after,
    run_guarded,
)
from trainsync.sync.context import SyncDeps, worker_context
from trainsync.sync.queue import ArqJobQueue

log = get_logger(__name__)

OVERLAP = timedelta(days=2)
CRON_MINUTES = {0, 30}
NEEDS_BACKFILL = "needs_backfill"
_BACKFILL_OPEN = (SyncStatus.RUNNING, SyncStatus.PAUSED)


async def run_incremental(
    deps: SyncDeps, athlete_id: int, *, per_page: int = PER_PAGE
) -> SyncOutcome:
    claim = await _claim(deps, athlete_id)
    if isinstance(claim, SyncOutcome):
        return claim
    run_id, after, first_page = claim
    runs = RunWriter(deps, run_id)

    async def pages() -> SyncOutcome:
        page_no = first_page
        while True:
            await ensure_budget(deps.budget, "low")
            page = await deps.strava.list_activities(
                athlete_id, after=after, page=page_no, per_page=per_page, priority="low"
            )
            if not page:
                break
            page_no += 1
            await runs.store_page(athlete_id, page, {"after": after, "page": page_no})
        await runs.finish(SyncStatus.SUCCEEDED)
        return SyncOutcome("succeeded", run_id)

    return await run_guarded(runs, "incremental", athlete_id, pages)


async def _claim(deps: SyncDeps, athlete_id: int) -> tuple[int, int, int] | SyncOutcome:
    now = deps.clock()
    async with deps.sessionmaker.begin() as session:
        athlete = await session.get(Athlete, athlete_id)
        if athlete is None or not athlete.active:
            return SyncOutcome("skipped")
        repo = SyncRunRepository(session)
        if await repo.open_run(athlete_id, SyncKind.BACKFILL) is not None:
            log.info("incremental_skipped_backfill_open", athlete_id=athlete_id)
            return SyncOutcome("skipped")
        run = await repo.open_run(athlete_id, SyncKind.INCREMENTAL, lock=True)
        if run is not None and is_live(run, now, STALE_AFTER):
            return SyncOutcome("already_running", run.id)
        if run is not None:
            await repo.set_status(run.id, SyncStatus.RUNNING, now)
            return run.id, int(run.cursor["after"]), int(run.cursor.get("page", 1))

        latest = await ActivityRepository(session).max_start_date(athlete_id)
        if latest is None and not await repo.has_succeeded(athlete_id, SyncKind.BACKFILL):
            return SyncOutcome(NEEDS_BACKFILL)
        # No activities after a finished backfill: the whole (empty) history is cheap to ask for.
        after = 0 if latest is None else int((latest - OVERLAP).timestamp())
        run = await repo.create(athlete_id, SyncKind.INCREMENTAL, {"after": after, "page": 1}, now)
        return run.id, after, 1


async def incremental_sync(ctx: dict[str, Any], athlete_id: int) -> str:
    wc = worker_context(ctx)
    outcome = await run_incremental(wc.sync_deps(), athlete_id)
    if outcome.status == NEEDS_BACKFILL:
        await ArqJobQueue(wc.redis).enqueue_backfill(athlete_id)
        return "backfill_enqueued"
    retry = retry_after(outcome.resume_at, wc.clock())
    if retry is not None:
        raise retry
    return outcome.status


incremental_job = func(incremental_sync, name="incremental_sync", max_tries=SYNC_MAX_TRIES)


# ------------------------------------------------------------------------- cron


def window_key(now: datetime) -> str:
    """The cron slot `now` belongs to (UTC, 30-minute granularity), e.g. `202610181230`."""
    slot = now.replace(minute=now.minute - now.minute % 30, second=0, microsecond=0)
    return slot.strftime("%Y%m%d%H%M")


def incremental_job_id(athlete_id: int, now: datetime) -> str:
    return f"incremental:{athlete_id}:{window_key(now)}"


async def athletes_due(sessionmaker: async_sessionmaker[AsyncSession]) -> list[int]:
    """Active athletes without a backfill still running or paused."""
    open_backfill = select(SyncRun.athlete_id).where(
        SyncRun.kind == SyncKind.BACKFILL, SyncRun.status.in_(_BACKFILL_OPEN)
    )
    async with sessionmaker() as session:
        rows = await session.scalars(
            select(Athlete.id)
            .where(Athlete.active, Athlete.id.not_in(open_backfill))
            .order_by(Athlete.id)
        )
        return list(rows.all())


async def enqueue_incremental_jobs(
    sessionmaker: async_sessionmaker[AsyncSession], pool: ArqRedis, now: datetime
) -> list[int]:
    """Enqueue one `incremental_sync` per due athlete; returns the athletes newly enqueued.

    The job id carries the window, so a second scheduler run in the same window is a no-op.
    """
    enqueued = []
    for athlete_id in await athletes_due(sessionmaker):
        job = await pool.enqueue_job(
            "incremental_sync", athlete_id, _job_id=incremental_job_id(athlete_id, now)
        )
        if job is not None:
            enqueued.append(athlete_id)
    log.info("incremental_scheduled", window=window_key(now), athletes=len(enqueued))
    return enqueued


async def schedule_incremental(ctx: dict[str, Any]) -> int:
    wc = worker_context(ctx)
    return len(await enqueue_incremental_jobs(wc.sessionmaker, wc.redis, wc.clock()))


incremental_cron = cron(
    schedule_incremental,
    name="schedule_incremental",
    minute=CRON_MINUTES,
    run_at_startup=False,
)
