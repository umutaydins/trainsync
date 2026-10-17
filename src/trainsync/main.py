"""FastAPI app factory.

Run with `uvicorn trainsync.main:create_app --factory`. There is deliberately no module-level
`app`, so importing this module never needs the environment to be configured.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from trainsync import __version__
from trainsync.api import health
from trainsync.api.middleware import RequestIdMiddleware
from trainsync.core.logging import configure_logging, get_logger
from trainsync.core.redis import create_redis
from trainsync.core.settings import Settings, get_settings
from trainsync.db.session import create_engine, create_sessionmaker

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
            log.info("app_startup", env=settings.env)
            yield
            log.info("app_shutdown")

    app = FastAPI(title="trainsync", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    return app
