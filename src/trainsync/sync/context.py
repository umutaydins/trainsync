"""Typed access to the per-worker resources that `trainsync.worker.startup` puts into arq's ctx."""

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Protocol

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock, Sleep
from trainsync.core.settings import Settings
from trainsync.strava.budget import Budget, Priority
from trainsync.strava.client import StravaClient
from trainsync.strava.models import StravaActivity
from trainsync.strava.tokens import TokenManager

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


def worker_context(ctx: dict[str, Any]) -> WorkerContext:
    context: WorkerContext = ctx[CTX_KEY]
    return context
