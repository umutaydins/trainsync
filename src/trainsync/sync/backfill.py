"""Resumable backfill of an athlete's full history.

Pages are requested newest-first with a time cursor (`before=<unix>`, always `page=1`) instead of
page numbers, so activities uploaded mid-backfill don't shift pages. Each page is upserted in the
same transaction that advances `sync_runs.cursor`, so a crash at any point resumes from the last
committed page; re-fetching that one page is harmless because upserts are idempotent.

The next cursor is `oldest start_date on the page + 1 s`, so activities sharing the boundary
second are fetched again rather than skipped.
"""

from typing import Any

from arq.worker import func

from trainsync.core.logging import get_logger
from trainsync.db.models import Athlete, SyncKind, SyncStatus
from trainsync.db.repositories.sync_runs import SyncRunRepository, is_live
from trainsync.strava.models import StravaActivity
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

log = get_logger(__name__)

__all__ = ["STALE_AFTER", "backfill", "backfill_job", "next_cursor", "run_backfill"]


async def run_backfill(deps: SyncDeps, athlete_id: int, *, per_page: int = PER_PAGE) -> SyncOutcome:
    claim = await _claim(deps, athlete_id)
    if isinstance(claim, SyncOutcome):
        return claim
    run_id, before = claim
    runs = RunWriter(deps, run_id)

    async def pages() -> SyncOutcome:
        cursor = before
        while True:
            await ensure_budget(deps.budget, "low")
            page = await deps.strava.list_activities(
                athlete_id, before=cursor, per_page=per_page, priority="low"
            )
            if not page:
                break
            next_before, done = next_cursor(page, cursor, per_page)
            await runs.store_page(athlete_id, page, {"before": next_before})
            if done:
                break
            cursor = next_before
        await runs.finish(SyncStatus.SUCCEEDED)
        return SyncOutcome("succeeded", run_id)

    return await run_guarded(runs, "backfill", athlete_id, pages)


def next_cursor(page: list[StravaActivity], before: int | None, per_page: int) -> tuple[int, bool]:
    """Next `before` and whether the history is exhausted."""
    oldest = min(int(a.start_date.timestamp()) for a in page)
    candidate = oldest + 1
    if before is None or candidate < before:
        return candidate, False
    # No progress: the page only repeated activities at the boundary second.
    if len(page) < per_page:
        return candidate, True
    # A full page of activities in one second: step past it (more ties than a page are lost).
    return oldest, False


async def _claim(deps: SyncDeps, athlete_id: int) -> tuple[int, int | None] | SyncOutcome:
    now = deps.clock()
    async with deps.sessionmaker.begin() as session:
        athlete = await session.get(Athlete, athlete_id)
        if athlete is None or not athlete.active:
            log.info("backfill_skipped_inactive", athlete_id=athlete_id)
            return SyncOutcome("skipped")
        repo = SyncRunRepository(session)
        run = await repo.open_run(athlete_id, SyncKind.BACKFILL, lock=True)
        if run is not None and is_live(run, now, STALE_AFTER):
            log.info("backfill_already_running", athlete_id=athlete_id, run_id=run.id)
            return SyncOutcome("already_running", run.id)
        if run is None:
            run = await repo.create(athlete_id, SyncKind.BACKFILL, {"before": None}, now)
        else:
            await repo.set_status(run.id, SyncStatus.RUNNING, now)
        before: int | None = run.cursor.get("before")
        return run.id, before


async def backfill(ctx: dict[str, Any], athlete_id: int) -> str:
    wc = worker_context(ctx)
    outcome = await run_backfill(wc.sync_deps(), athlete_id)
    retry = retry_after(outcome.resume_at, wc.clock())
    if retry is not None:
        raise retry
    return outcome.status


backfill_job = func(backfill, name="backfill", max_tries=SYNC_MAX_TRIES)
