"""FastAPI dependencies that hand out the per-process resources created in the lifespan."""

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.crypto import TokenCipher
from trainsync.core.settings import Settings
from trainsync.strava.client import StravaClient
from trainsync.sync.queue import JobQueue


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


def get_strava_client(request: Request) -> StravaClient:
    client: StravaClient = request.app.state.strava
    return client


def get_job_queue(request: Request) -> JobQueue:
    queue: JobQueue = request.app.state.job_queue
    return queue


_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="One of the keys configured in `API_KEYS`.",
)


def require_api_key(
    request: Request, api_key: Annotated[str | None, Security(_api_key_header)]
) -> None:
    """`401` unless `X-API-Key` matches a configured key (constant-time, every key compared)."""
    settings: Settings = request.app.state.settings
    supplied = (api_key or "").encode()
    matched = False
    for key in settings.api_keys:
        matched |= hmac.compare_digest(supplied, key.get_secret_value().encode())
    if not api_key or not matched:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing or invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
CipherDep = Annotated[TokenCipher, Depends(get_cipher)]
StravaDep = Annotated[StravaClient, Depends(get_strava_client)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
