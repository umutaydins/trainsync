"""FastAPI dependencies that hand out the per-process resources created in the lifespan."""

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.crypto import TokenCipher
from trainsync.core.jobs import CoachEvents, JobQueue
from trainsync.core.settings import Settings


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    return sessionmaker


def get_cipher(request: Request) -> TokenCipher:
    cipher: TokenCipher = request.app.state.cipher
    return cipher


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def get_coach_events(request: Request) -> CoachEvents:
    events: CoachEvents = request.app.state.job_queue
    return events


def get_job_queue(request: Request) -> JobQueue:
    queue: JobQueue = request.app.state.job_queue
    return queue


API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="One of the keys configured in `API_KEYS` (machine and owner tooling).",
)


def key_matches(supplied: str | None, keys: list[SecretStr]) -> bool:
    """Constant-time: every configured key is compared, whatever matches first."""
    raw = (supplied or "").encode()
    matched = False
    for key in keys:
        matched |= hmac.compare_digest(raw, key.get_secret_value().encode())
    return bool(supplied) and matched


def require_api_key(
    request: Request, api_key: Annotated[str | None, Security(API_KEY_HEADER)]
) -> None:
    """`401` unless `X-API-Key` matches a configured key."""
    settings: Settings = request.app.state.settings
    if not key_matches(api_key, settings.api_keys):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing or invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
CipherDep = Annotated[TokenCipher, Depends(get_cipher)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
CoachEventsDep = Annotated[CoachEvents, Depends(get_coach_events)]
RedisDep = Annotated[Redis, Depends(get_redis)]
