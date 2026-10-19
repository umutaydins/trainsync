"""Demo worker: `arq trainsync.entrypoints.demo.worker.DemoWorkerSettings` (P7.9, ADR 0028).

Only the nightly reset. No Strava sync, webhook retry, notifications or check-in prompts: the
demo athlete has no tokens and nobody to notify. Serves /metrics on WORKER_METRICS_PORT like
the real worker, so the image's healthcheck works unchanged.
"""

import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock, utc_now
from trainsync.core.db import create_engine, create_sessionmaker
from trainsync.core.logging import configure_logging, get_logger
from trainsync.core.settings import Settings, get_settings
from trainsync.entrypoints.demo.store import DemoModeRequiredError, reset

log = get_logger(__name__)

DEMO_CTX_KEY = "demo"
# arq runs crons in the worker's local time: UTC in the image. 03:00 UTC is after midnight in
# Europe/Istanbul (the default CHECKIN_TZ), so the reset moves the twelve weeks to the new day.
RESET_HOUR_UTC = 3
_DEFAULT_REDIS_URL: str = Settings.model_fields["redis_url"].default


@dataclass(frozen=True, slots=True)
class DemoDeps:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    clock: Clock
    exit_stack: AsyncExitStack


async def startup(ctx: dict[str, Any]) -> None:
    """`ctx` may carry pre-built `settings` / `clock` (tests); otherwise defaults."""
    settings: Settings = ctx.get("settings") or get_settings()
    configure_logging(settings)
    if not settings.demo_mode:
        raise DemoModeRequiredError("the demo worker only runs with DEMO_MODE=true")
    stack = AsyncExitStack()
    engine = create_engine(settings)
    stack.push_async_callback(engine.dispose)
    if settings.worker_metrics_port:
        server, _ = start_http_server(settings.worker_metrics_port)
        stack.callback(server.server_close)
        stack.callback(server.shutdown)
    clock: Clock = ctx.get("clock") or utc_now
    ctx[DEMO_CTX_KEY] = DemoDeps(settings, create_sessionmaker(engine), clock, stack)
    log.info("demo_worker_startup", reset_hour_utc=RESET_HOUR_UTC)


async def shutdown(ctx: dict[str, Any]) -> None:
    deps: DemoDeps | None = ctx.get(DEMO_CTX_KEY)
    if deps is not None:
        await deps.exit_stack.aclose()


async def demo_reset_job(ctx: dict[str, Any]) -> int:
    """Wipe and re-seed; returns the number of activities written."""
    deps: DemoDeps = ctx[DEMO_CTX_KEY]
    summary = await reset(deps.settings, deps.sessionmaker, deps.clock)
    return summary.activities


demo_reset_cron = cron(
    demo_reset_job,
    name="demo_reset",
    hour={RESET_HOUR_UTC},
    minute={0},
    run_at_startup=False,
)


class DemoWorkerSettings:
    functions: ClassVar[list[Any]] = [demo_reset_job]
    cron_jobs: ClassVar[list[Any]] = [demo_reset_cron]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL))
    max_jobs = 1
    job_timeout = 300
    max_tries = 3
