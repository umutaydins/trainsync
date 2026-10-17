"""arq worker entry point: `arq trainsync.worker.WorkerSettings`.

Shared resources (DB engine, Redis, the one httpx client, TokenManager, StravaClient) are created
in `startup` and closed in `shutdown`; jobs reach them through the typed `WorkerContext`.
"""

import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, ClassVar

from arq.connections import ArqRedis, RedisSettings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.logging import configure_logging, get_logger
from trainsync.core.settings import Settings, get_settings
from trainsync.db.repositories.tokens import SqlTokenStore
from trainsync.db.session import create_engine, create_sessionmaker
from trainsync.strava.client import StravaClient
from trainsync.strava.http import build_http_client
from trainsync.strava.tokens import RedisRefreshLock, TokenManager

log = get_logger(__name__)

_DEFAULT_REDIS_URL: str = Settings.model_fields["redis_url"].default
_CTX_KEY = "trainsync"


@dataclass(frozen=True, slots=True)
class WorkerContext:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: ArqRedis
    strava: StravaClient
    tokens: TokenManager
    clock: Clock
    sleep: Sleep
    exit_stack: AsyncExitStack


def worker_context(ctx: dict[str, Any]) -> WorkerContext:
    context: WorkerContext = ctx[_CTX_KEY]
    return context


async def startup(ctx: dict[str, Any]) -> None:
    """`ctx` may carry pre-built `settings` / `clock` / `sleep` (tests); otherwise defaults."""
    settings: Settings = ctx.get("settings") or get_settings()
    configure_logging(settings)
    clock: Clock = ctx.get("clock") or utc_now
    sleep: Sleep = ctx.get("sleep") or real_sleep
    redis: ArqRedis = ctx["redis"]

    stack = AsyncExitStack()
    engine = create_engine(settings)
    stack.push_async_callback(engine.dispose)
    sessionmaker = create_sessionmaker(engine)
    http = build_http_client(settings)
    stack.push_async_callback(http.aclose)

    strava = StravaClient(http, settings, clock=clock, sleep=sleep)
    tokens = TokenManager(
        SqlTokenStore(sessionmaker, TokenCipher.from_settings(settings)),
        RedisRefreshLock(redis),
        strava,
        clock=clock,
        sleep=sleep,
    )
    strava.with_token_provider(tokens)
    ctx[_CTX_KEY] = WorkerContext(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        redis=redis,
        strava=strava,
        tokens=tokens,
        clock=clock,
        sleep=sleep,
        exit_stack=stack,
    )
    log.info("worker_startup", env=settings.env)


async def shutdown(ctx: dict[str, Any]) -> None:
    context: WorkerContext | None = ctx.get(_CTX_KEY)
    if context is not None:
        await context.exit_stack.aclose()
    log.info("worker_shutdown")


async def ping(ctx: dict[str, Any]) -> str:
    return "pong"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL))
    max_jobs = 10
    job_timeout = 1800  # a full backfill of a long history can take a while
    max_tries = 5
    keep_result = 3600
