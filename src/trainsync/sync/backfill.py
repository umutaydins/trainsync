"""Resumable backfill of an athlete's full history.

Pages are requested newest-first with a time cursor (`before=<unix>`, always `page=1`) instead of
page numbers, so activities uploaded mid-backfill don't shift pages. Each page is upserted in the
same transaction that advances `sync_runs.cursor`, so a crash at any point resumes from the last
committed page; re-fetching that one page is harmless because upserts are idempotent.

The next cursor is `oldest start_date on the page + 1 s`, so activities sharing the boundary
second are fetched again rather than skipped.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from arq import Retry
from arq.worker import func

from trainsync.core.logging import get_logger
from trainsync.db.models import Athlete, SyncKind, SyncStatus
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.sync_runs import SyncRunRepository, is_live
from trainsync.strava.budget import Budget, Priority
from trainsync.strava.errors import CircuitOpen, RateLimited, StravaAuthError
from trainsync.strava.models import StravaActivity
from trainsync.sync.context import SyncDeps, worker_context

log = get_logger(__name__)

PER_PAGE = 200
# A `running` run without a checkpoint for this long belongs to a worker that died.
STALE_AFTER = timedelta(minutes=5)
# Rate-limit / breaker deferrals go through arq `Retry`, which counts as a try.
SYNC_MAX_TRIES = 1000
_MAX_ERROR_LEN = 500


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    status: str
    run_id: int | None = None
    resume_at: datetime | None = None


class _BudgetDeferralError(Exception):
    """The budget said "not now"; handled like a rate limit."""

    def __init__(self, resume_at: datetime) -> None:
        self.resume_at = resume_at


async def run_backfill(deps: SyncDeps, athlete_id: int, *, per_page: int = PER_PAGE) -> SyncOutcome:
    claim = await _claim(deps, athlete_id)
    if isinstance(claim, SyncOutcome):
        return claim
    run_id, before = claim
    runs = _Runs(deps, run_id)
    try:
        while True:
            await ensure_budget(deps.budget, "low")
            page = await deps.strava.list_activities(
                athlete_id, before=before, per_page=per_page, priority="low"
            )
            if not page:
                await runs.finish(SyncStatus.SUCCEEDED)
                return SyncOutcome("succeeded", run_id)
            next_before, done = next_cursor(page, before, per_page)
            await _store_page(deps, run_id, athlete_id, page, {"before": next_before})
            if done:
                await runs.finish(SyncStatus.SUCCEEDED)
                return SyncOutcome("succeeded", run_id)
            before = next_before
    except (RateLimited, CircuitOpen, _BudgetDeferralError) as exc:
        resume_at = deferral_time(exc)
        await runs.finish(SyncStatus.PAUSED)
        log.info("backfill_paused", athlete_id=athlete_id, resume_at=resume_at)
        return SyncOutcome("paused", run_id, resume_at)
    except StravaAuthError as exc:
        await runs.finish(SyncStatus.FAILED, error=short_error(exc))
        log.warning("backfill_auth_failed", athlete_id=athlete_id)
        return SyncOutcome("failed", run_id)
    except asyncio.CancelledError:
        await runs.finish(SyncStatus.PAUSED)  # worker shutdown / timeout: resume next time
        raise
    except Exception as exc:
        await runs.finish(SyncStatus.FAILED, error=short_error(exc))
        raise


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


async def ensure_budget(budget: Budget, priority: Priority) -> None:
    allowance = await budget.allow(priority)
    if not allowance.allowed:
        if allowance.resume_at is None:
            raise RuntimeError("budget denied a call without a resume time")
        raise _BudgetDeferralError(allowance.resume_at)


def deferral_time(exc: RateLimited | CircuitOpen | _BudgetDeferralError) -> datetime:
    if isinstance(exc, RateLimited):
        return exc.reset_at
    if isinstance(exc, CircuitOpen):
        return exc.retry_at
    return exc.resume_at


def short_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LEN]


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


async def _store_page(
    deps: SyncDeps,
    run_id: int,
    athlete_id: int,
    page: list[StravaActivity],
    cursor: dict[str, Any],
) -> None:
    async with deps.sessionmaker.begin() as session:
        upserted = await ActivityRepository(session).upsert_many(athlete_id, page)
        await SyncRunRepository(session).checkpoint(run_id, cursor, upserted, deps.clock())


@dataclass(frozen=True, slots=True)
class _Runs:
    deps: SyncDeps
    run_id: int

    async def finish(self, status: SyncStatus, *, error: str | None = None) -> None:
        async with self.deps.sessionmaker.begin() as session:
            await SyncRunRepository(session).set_status(
                self.run_id, status, self.deps.clock(), error=error
            )


def retry_after(outcome: SyncOutcome, now: datetime) -> Retry | None:
    """An arq `Retry` that re-runs this job when the deferral is over."""
    if outcome.resume_at is None:
        return None
    return Retry(defer=max(outcome.resume_at - now, timedelta(0)) + timedelta(seconds=1))


async def backfill(ctx: dict[str, Any], athlete_id: int) -> str:
    wc = worker_context(ctx)
    outcome = await run_backfill(wc.sync_deps(), athlete_id)
    retry = retry_after(outcome, wc.clock())
    if retry is not None:
        raise retry
    return outcome.status


backfill_job = func(backfill, name="backfill", max_tries=SYNC_MAX_TRIES)
