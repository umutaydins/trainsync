"""FastAPI dependencies that hand out the per-process resources created in the lifespan."""

from typing import Annotated

from fastapi import Depends, Request
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


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
CipherDep = Annotated[TokenCipher, Depends(get_cipher)]
StravaDep = Annotated[StravaClient, Depends(get_strava_client)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
