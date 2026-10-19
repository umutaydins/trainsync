"""Typed access to the per-worker resources that `trainsync.entrypoints.worker.settings.startup`
puts into arq's ctx."""

from collections.abc import Iterator
from contextlib import AsyncExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock, Sleep
from trainsync.core.settings import Settings
from trainsync.integrations.strava.budget import Budget, Priority
from trainsync.integrations.strava.client import StravaClient
from trainsync.integrations.strava.models import StravaActivity
from trainsync.modules.strava.tokens import TokenManager

CTX_KEY = "trainsync"


class ActivitySource(Protocol):
    async def list_activities(
        self,
        athlete_id: int,
        *,
        before: int | None = None,
        after: int | None = None,
        page: int = 1,
        per_page: int = 200,
        priority: Priority = "low",
    ) -> list[StravaActivity]: ...


@dataclass(frozen=True, slots=True)
class SyncDeps:
    """What a sync job needs; jobs get it from the worker, tests build it from stubs."""

    sessionmaker: async_sessionmaker[AsyncSession]
    strava: ActivitySource
    budget: Budget
    clock: Clock


@dataclass(frozen=True, slots=True)
class WorkerContext:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: ArqRedis
    strava: StravaClient
    tokens: TokenManager
    budget: Budget
    clock: Clock
    sleep: Sleep
    exit_stack: AsyncExitStack

    def sync_deps(self) -> SyncDeps:
        return SyncDeps(self.sessionmaker, self.strava, self.budget, self.clock)


@contextmanager
def job_log_context(ctx: dict[str, Any], job_name: str, **ids: int) -> Iterator[None]:
    """Bind `job_id`, `job_name` and the job's ids (e.g. `athlete_id`) to every log line.

    arq runs each job in its own asyncio task, so the binding stays inside this job."""
    with structlog.contextvars.bound_contextvars(
        job_id=ctx.get("job_id"), job_name=job_name, **ids
    ):
        yield


def worker_context(ctx: dict[str, Any]) -> WorkerContext:
    context: WorkerContext = ctx[CTX_KEY]
    return context
