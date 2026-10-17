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
from trainsync.core.settings import Settings, get_settings

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            app.state.exit_stack = stack
            log.info("app_startup", env=settings.env)
            yield
            log.info("app_shutdown")

    app = FastAPI(title="trainsync", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    return app
