"""arq worker entry point: `arq trainsync.worker.WorkerSettings`.

Shared resources (DB engine, Redis, the one httpx client, TokenManager, StravaClient) are created
in `startup` and closed in `shutdown`; jobs reach them through the typed `WorkerContext`.
"""

import os
from contextlib import AsyncExitStack
from typing import Any, ClassVar

from arq.connections import ArqRedis, RedisSettings
from prometheus_client import start_http_server

from trainsync.bot.messages import messages_for
from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.logging import configure_logging, get_logger, warn_dev_secrets
from trainsync.core.settings import Settings, get_settings
from trainsync.db.repositories.tokens import SqlTokenStore
from trainsync.db.session import create_engine, create_sessionmaker
from trainsync.notify.alerts import ALERTS_CTX_KEY, alerts_cron, build_alert_deps
from trainsync.notify.checkin import CHECKIN_CTX_KEY, build_checkin_deps, checkin_cron
from trainsync.notify.jobs import (
    NOTIFY_CTX_KEY,
    NotifyDeps,
    build_notifier,
    notify_new_activity_job,
)
from trainsync.strava.breaker_status import RedisBreakerPublisher, process_name
from trainsync.strava.budget import RateBudget
from trainsync.strava.client import StravaClient
from trainsync.strava.http import build_http_client
from trainsync.strava.tokens import RedisRefreshLock, TokenManager
from trainsync.sync.backfill import backfill_job
from trainsync.sync.context import CTX_KEY, WorkerContext
from trainsync.sync.incremental import incremental_cron, incremental_job
from trainsync.sync.webhook_retry import retry_webhooks_cron
from trainsync.sync.webhooks import process_webhook_event_job

log = get_logger(__name__)

_DEFAULT_REDIS_URL: str = Settings.model_fields["redis_url"].default


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

    if settings.worker_metrics_port:
        # One registry per process (ADR 0010); Prometheus scrapes each worker on this port.
        server, _ = start_http_server(settings.worker_metrics_port)
        stack.callback(server.server_close)  # LIFO: runs after shutdown()
        stack.callback(server.shutdown)
    budget = RateBudget(redis, clock)
    strava = StravaClient(
        http,
        settings,
        clock=clock,
        sleep=sleep,
        budget=budget,
        breaker_listener=RedisBreakerPublisher(redis, process_name("worker"), clock),
    )
    tokens = TokenManager(
        SqlTokenStore(sessionmaker, TokenCipher.from_settings(settings)),
        RedisRefreshLock(redis),
        strava,
        clock=clock,
        sleep=sleep,
    )
    strava.with_token_provider(tokens)
    ctx[CTX_KEY] = WorkerContext(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        redis=redis,
        strava=strava,
        tokens=tokens,
        budget=budget,
        clock=clock,
        sleep=sleep,
        exit_stack=stack,
    )
    notifier, chat_ref = build_notifier(settings, http, sleep)
    ctx[NOTIFY_CTX_KEY] = NotifyDeps(
        sessionmaker,
        notifier,
        chat_ref,
        settings.dashboard_public_url,
        clock,
        messages_for(settings),
    )
    ctx[ALERTS_CTX_KEY] = build_alert_deps(settings, sessionmaker, redis, notifier, chat_ref, clock)
    ctx[CHECKIN_CTX_KEY] = build_checkin_deps(
        settings, sessionmaker, http, clock, sleep, messages_for(settings)
    )
    log.info(
        "worker_startup",
        env=settings.env,
        notifier=notifier.channel,
        checkin=settings.checkin_active,
        alerts=chat_ref is not None,
        backup_dir=settings.backup_dir or None,
    )
    warn_dev_secrets(settings, log)


async def shutdown(ctx: dict[str, Any]) -> None:
    context: WorkerContext | None = ctx.get(CTX_KEY)
    if context is not None:
        await context.exit_stack.aclose()
    log.info("worker_shutdown")


async def ping(ctx: dict[str, Any]) -> str:
    return "pong"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        ping,
        backfill_job,
        incremental_job,
        process_webhook_event_job,
        notify_new_activity_job,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        incremental_cron,
        retry_webhooks_cron,
        checkin_cron,
        alerts_cron,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL))
    max_jobs = 10
    job_timeout = 1800  # a full backfill of a long history can take a while
    max_tries = 5
    keep_result = 3600
