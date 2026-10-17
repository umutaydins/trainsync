"""Health endpoints."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from trainsync.core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
log = get_logger(__name__)

CHECK_TIMEOUT_S = 1.0


@router.get("/live", summary="Liveness: the process is up")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness: PostgreSQL and Redis are reachable",
    responses={
        200: {
            "content": {
                "application/json": {"example": {"status": "ok", "db": "ok", "redis": "ok"}}
            }
        },
        503: {
            "description": "A dependency is unreachable",
            "content": {
                "application/json": {"example": {"status": "error", "db": "ok", "redis": "error"}}
            },
        },
    },
)
async def ready(request: Request) -> JSONResponse:
    engine: AsyncEngine = request.app.state.engine
    redis: Redis = request.app.state.redis
    db_ok, redis_ok = await asyncio.gather(
        _check("db", lambda: _ping_db(engine)),
        _check("redis", lambda: _ping_redis(redis)),
    )
    body = {
        "status": "ok" if db_ok and redis_ok else "error",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    return JSONResponse(body, status_code=200 if db_ok and redis_ok else 503)


async def _ping_db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _ping_redis(redis: Redis) -> None:
    await redis.ping()


async def _check(component: str, probe: Callable[[], Awaitable[None]]) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            await probe()
    except Exception as exc:
        # Only the exception type: messages can contain connection strings.
        log.warning("readiness_check_failed", component=component, error_type=type(exc).__name__)
        return False
    return True
