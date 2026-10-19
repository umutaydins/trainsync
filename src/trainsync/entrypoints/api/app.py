"""FastAPI app factory.

Run with `uvicorn trainsync.entrypoints.api.app:create_app --factory`. There is deliberately no
module-level `app`, so importing this module never needs the environment to be configured.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from trainsync import __version__
from trainsync.core.clock import utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.db import create_engine, create_sessionmaker
from trainsync.core.errors import VALIDATION_ERROR_EXAMPLE
from trainsync.core.http import build_http_client
from trainsync.core.jobs import ArqJobQueue, create_arq_redis
from trainsync.core.logging import configure_logging, get_logger, warn_dev_secrets
from trainsync.core.redis import create_redis
from trainsync.core.settings import Settings, get_settings
from trainsync.entrypoints.api import health
from trainsync.entrypoints.api.middleware import (
    DemoReadOnlyMiddleware,
    MetricsMiddleware,
    RequestIdMiddleware,
)
from trainsync.integrations.openfoodfacts.client import OpenFoodFactsClient
from trainsync.integrations.strava.breaker_status import RedisBreakerPublisher, process_name
from trainsync.integrations.strava.client import StravaClient
from trainsync.modules.activities import router as activities
from trainsync.modules.admin import router as admin
from trainsync.modules.auth import router as accounts
from trainsync.modules.chat import router as chats
from trainsync.modules.checkin import router as checkins
from trainsync.modules.nutrition import router as nutrition
from trainsync.modules.stats import router as stats
from trainsync.modules.strava import router as auth
from trainsync.modules.sync import router as sync_status
from trainsync.modules.sync import webhook_router as webhooks
from trainsync.modules.training import router as training
from trainsync.modules.users import router as me

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            app.state.exit_stack = stack
            engine = create_engine(settings)
            stack.push_async_callback(engine.dispose)
            app.state.engine = engine
            app.state.sessionmaker = create_sessionmaker(engine)
            redis = create_redis(settings)
            stack.push_async_callback(redis.aclose)
            app.state.redis = redis
            arq_pool = create_arq_redis(settings)
            stack.push_async_callback(arq_pool.aclose)
            app.state.job_queue = ArqJobQueue(arq_pool)
            http = build_http_client(settings)
            stack.push_async_callback(http.aclose)
            # The API only exchanges OAuth codes; API calls with tokens happen in the worker.
            app.state.strava = StravaClient(
                http,
                settings,
                breaker_listener=RedisBreakerPublisher(redis, process_name("api")),
            )
            # Food lookup (P6.4): the same shared client, its own timeout per request.
            app.state.openfoodfacts = OpenFoodFactsClient(http, settings)
            log.info("app_startup", env=settings.env, demo_mode=settings.demo_mode)
            warn_dev_secrets(settings, log)
            yield
            log.info("app_shutdown")

    app = FastAPI(title="trainsync", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = utc_now
    app.state.cipher = TokenCipher.from_settings(settings)
    if settings.demo_mode:
        # Innermost: a refused write is still timed and carries its request id.
        app.add_middleware(DemoReadOnlyMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(me.router)
    app.include_router(admin.router)
    app.include_router(auth.router)
    app.include_router(auth.me_router)
    app.include_router(webhooks.router)
    app.include_router(activities.router)
    app.include_router(stats.router)
    app.include_router(sync_status.router)
    app.include_router(chats.me_router)
    app.include_router(chats.service_router)
    for router in training.ROUTERS:
        app.include_router(router)
    for router in nutrition.ROUTERS:
        app.include_router(router)
    app.include_router(checkins.router)
    _document_validation_errors(app)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def _document_validation_errors(app: FastAPI) -> None:
    """Give FastAPI's generated 422 schema an example, like every other response."""
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = default_openapi()
            components = schema.get("components", {}).get("schemas", {})
            if "HTTPValidationError" in components:
                components["HTTPValidationError"]["examples"] = [VALIDATION_ERROR_EXAMPLE]
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
