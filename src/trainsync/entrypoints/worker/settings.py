"""arq worker entry point: `arq trainsync.entrypoints.worker.settings.WorkerSettings`.

Shared resources (DB engine, Redis, the one httpx client, TokenManager, StravaClient) are created
in `startup` and closed in `shutdown`; jobs reach them through the typed `WorkerContext`.
"""

import os
from contextlib import AsyncExitStack
from typing import Any, ClassVar

from arq.connections import ArqRedis, RedisSettings
from prometheus_client import start_http_server

from trainsync.core.clock import Clock, Sleep, real_sleep, utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.db import create_engine, create_sessionmaker
from trainsync.core.http import build_http_client
from trainsync.core.logging import configure_logging, get_logger, warn_dev_secrets
from trainsync.core.settings import Settings, get_settings
from trainsync.integrations.strava.breaker_status import RedisBreakerPublisher, process_name
from trainsync.integrations.strava.budget import RateBudget
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.coach.packs import messages_for
from trainsync.modules.coach.voice import build_voice
from trainsync.modules.notifications.alerts import ALERTS_CTX_KEY, alerts_cron, build_alert_deps
from trainsync.modules.notifications.checkin import (
    CHECKIN_CTX_KEY,
    build_checkin_deps,
    checkin_cron,
)
from trainsync.modules.notifications.coach import (
    COACH_CTX_KEY,
    COACH_JOBS,
    build_coach_deps,
    coach_cron,
)
from trainsync.modules.notifications.digest import (
    DIGEST_CTX_KEY,
    build_digest_deps,
    digest_cron,
)
from trainsync.modules.notifications.tasks import (
    NOTIFY_CTX_KEY,
    NotifyDeps,
    build_notifier,
    notify_new_activity_job,
)
from trainsync.modules.strava.token_repository import SqlTokenStore
from trainsync.modules.strava.tokens import RedisRefreshLock, TokenManager
from trainsync.modules.sync.backfill import backfill_job
from trainsync.modules.sync.context import CTX_KEY, WorkerContext
from trainsync.modules.sync.disconnect import strava_disconnect_job
from trainsync.modules.sync.incremental import incremental_cron, incremental_job
from trainsync.modules.sync.webhook_retry import retry_webhooks_cron
from trainsync.modules.sync.webhooks import process_webhook_event_job
from trainsync.modules.users.lifecycle import purge_user_job

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
    msg = messages_for(settings)
    voice = build_voice(settings, redis, msg)
    ctx[NOTIFY_CTX_KEY] = NotifyDeps(sessionmaker, notifier, settings, clock, msg, voice)
    ctx[ALERTS_CTX_KEY] = build_alert_deps(settings, sessionmaker, redis, notifier, chat_ref, clock)
    ctx[CHECKIN_CTX_KEY] = build_checkin_deps(
        settings, sessionmaker, http, clock, sleep, msg, voice
    )
    ctx[DIGEST_CTX_KEY] = build_digest_deps(
        settings, sessionmaker, http, redis, clock, sleep, msg, voice
    )
    ctx[COACH_CTX_KEY] = build_coach_deps(
        settings, sessionmaker, http, redis, clock, sleep, messages_for(settings)
    )
    log.info(
        "worker_startup",
        env=settings.env,
        notifier=notifier.channel,
        checkin=settings.bot_enabled and settings.checkin_enabled is not False,
        coach=settings.bot_enabled and settings.coach_messages_enabled is not False,
        digests=settings.bot_enabled and settings.stats_digest_enabled is not False,
        intensity=settings.bot_intensity,
        profanity=settings.bot_profanity,
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
        strava_disconnect_job,
        purge_user_job,
        *COACH_JOBS,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        incremental_cron,
        retry_webhooks_cron,
        checkin_cron,
        alerts_cron,
        coach_cron,
        digest_cron,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL))
    max_jobs = 10
    job_timeout = 1800  # a full backfill of a long history can take a while
    max_tries = 5
    keep_result = 3600
