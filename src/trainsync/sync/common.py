"""Pieces shared by the sync jobs (backfill, incremental): budget checks, run bookkeeping and
the mapping of Strava errors to run states."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from arq import Retry

from trainsync.core.logging import get_logger
from trainsync.db.models import SyncStatus
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.sync_runs import SyncRunRepository
from trainsync.strava.budget import Budget, Priority
from trainsync.strava.errors import CircuitOpen, RateLimited, StravaAuthError, StravaUnavailable
from trainsync.strava.models import StravaActivity
from trainsync.sync.context import SyncDeps

log = get_logger(__name__)

PER_PAGE = 200
# A `running` run without a checkpoint for this long belongs to a worker that died.
STALE_AFTER = timedelta(minutes=5)
# Rate-limit / breaker deferrals go through arq `Retry`, which counts as a try.
SYNC_MAX_TRIES = 1000
# Strava down but the breaker still closed (retries exhausted): try again after this long.
UNAVAILABLE_DEFER = timedelta(seconds=30)
# Spreads deferred jobs out, so they don't all hit Strava in the same second when it comes back.
DEFER_JITTER_S = 1.0
_MAX_ERROR_LEN = 500


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    status: str
    run_id: int | None = None
    resume_at: datetime | None = None


class BudgetDeferralError(Exception):
    """The budget said "not now"; handled like a rate limit."""

    def __init__(self, resume_at: datetime) -> None:
        self.resume_at = resume_at


async def ensure_budget(budget: Budget, priority: Priority) -> None:
    allowance = await budget.allow(priority)
    if not allowance.allowed:
        if allowance.resume_at is None:
            raise RuntimeError("budget denied a call without a resume time")
        raise BudgetDeferralError(allowance.resume_at)


def deferral_time(exc: RateLimited | CircuitOpen | BudgetDeferralError) -> datetime:
    if isinstance(exc, RateLimited):
        return exc.reset_at
    if isinstance(exc, CircuitOpen):
        return exc.retry_at
    return exc.resume_at


def short_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LEN]


@dataclass(frozen=True, slots=True)
class RunWriter:
    deps: SyncDeps
    run_id: int

    async def finish(self, status: SyncStatus, *, error: str | None = None) -> None:
        async with self.deps.sessionmaker.begin() as session:
            await SyncRunRepository(session).set_status(
                self.run_id, status, self.deps.clock(), error=error
            )

    async def store_page(
        self, athlete_id: int, page: list[StravaActivity], cursor: dict[str, Any]
    ) -> None:
        """Upsert the page and advance the cursor in one transaction."""
        async with self.deps.sessionmaker.begin() as session:
            upserted = await ActivityRepository(session).upsert_many(athlete_id, page)
            await SyncRunRepository(session).checkpoint(
                self.run_id, cursor, upserted, self.deps.clock()
            )


async def run_guarded(
    runs: RunWriter, kind: str, athlete_id: int, body: Callable[[], Awaitable[SyncOutcome]]
) -> SyncOutcome:
    """Run the page loop, mapping errors to run states:
    rate limit / open circuit / budget / Strava unavailable → `paused` (+ resume time);
    auth → `failed`; cancellation → `paused` and re-raised; anything else → `failed` and
    re-raised."""
    try:
        return await body()
    except (RateLimited, CircuitOpen, BudgetDeferralError) as exc:
        return await _pause(runs, kind, athlete_id, deferral_time(exc))
    except StravaUnavailable:
        # A transient outage, not a broken job; repeated ones open the breaker.
        return await _pause(runs, kind, athlete_id, runs.deps.clock() + UNAVAILABLE_DEFER)
    except StravaAuthError as exc:
        await runs.finish(SyncStatus.FAILED, error=short_error(exc))
        log.warning(f"{kind}_auth_failed", athlete_id=athlete_id)
        return SyncOutcome("failed", runs.run_id)
    except asyncio.CancelledError:
        await runs.finish(SyncStatus.PAUSED)  # worker shutdown / timeout: resume next time
        raise
    except Exception as exc:
        await runs.finish(SyncStatus.FAILED, error=short_error(exc))
        raise


async def _pause(runs: RunWriter, kind: str, athlete_id: int, resume_at: datetime) -> SyncOutcome:
    await runs.finish(SyncStatus.PAUSED)
    log.info(f"{kind}_paused", athlete_id=athlete_id, resume_at=resume_at)
    return SyncOutcome("paused", runs.run_id, resume_at)


def retry_after(
    outcome: SyncOutcome, now: datetime, rng: random.Random | None = None
) -> Retry | None:
    """An arq `Retry` that re-runs this job when the deferral is over (plus up to
    `DEFER_JITTER_S` of jitter). arq counts it as a try, not a failure; `SYNC_MAX_TRIES` is
    high enough that deferrals never exhaust it."""
    if outcome.resume_at is None:
        return None
    jitter = (rng or random).uniform(0, DEFER_JITTER_S)
    delay = max(outcome.resume_at - now, timedelta(0)) + timedelta(seconds=1 + jitter)
    return Retry(defer=delay)
