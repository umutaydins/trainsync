"""FastAPI app factory.

Run with `uvicorn trainsync.main:create_app --factory`. There is deliberately no module-level
`app`, so importing this module never needs the environment to be configured.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from trainsync import __version__
from trainsync.api import activities, auth, health, webhooks
from trainsync.api.middleware import RequestIdMiddleware
from trainsync.core.clock import utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.logging import configure_logging, get_logger
from trainsync.core.redis import create_redis
from trainsync.core.settings import Settings, get_settings
from trainsync.db.session import create_engine, create_sessionmaker
from trainsync.strava.client import StravaClient
from trainsync.strava.http import build_http_client
from trainsync.sync.queue import ArqJobQueue, create_arq_redis

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
            app.state.strava = StravaClient(http, settings)
            log.info("app_startup", env=settings.env)
            yield
            log.info("app_shutdown")

    app = FastAPI(title="trainsync", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = utc_now
    app.state.cipher = TokenCipher.from_settings(settings)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(webhooks.router)
    app.include_router(activities.router)
    return app
