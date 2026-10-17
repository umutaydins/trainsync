"""Phase 2: SIGKILL a real arq worker mid-backfill; a new worker resumes the same run from its
cursor. fake_strava runs under uvicorn so both worker processes can reach it."""

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_ENV, fake_strava_login
from tests.support.factories import create_athlete
from trainsync.core.crypto import TokenCipher
from trainsync.core.settings import Settings
from trainsync.db.models import Activity, SyncRun
from trainsync.db.repositories.tokens import SqlTokenStore, Tokens
from trainsync.sync.common import STALE_AFTER
from trainsync.sync.queue import backfill_job_id, create_arq_redis

REPO_ROOT = Path(__file__).resolve().parents[2]
# Slow pages (~6 of 200) so the kill reliably lands mid-backfill.
LATENCY_MS = 600
ARQ_IN_PROGRESS_PREFIX = "arq:in-progress:"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture
def fake_strava_url() -> Iterator[str]:
    port = _free_port()
    env = {
        **os.environ,
        "FAKE_STRAVA_SEED_ACTIVITIES": "1000",
        "FAKE_STRAVA_RATE_LIMIT_15MIN": "100000",
        "FAKE_STRAVA_RATE_LIMIT_DAILY": "1000000",
        "FAKE_STRAVA_LATENCY_MS": str(LATENCY_MS),
    }
    proc = subprocess.Popen(  # noqa: S603  (fixed args, our own interpreter)
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fake_strava.app:create_app",
            "--factory",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(url, proc)
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _wait_until_up(url: str, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("fake_strava exited during startup")
        try:
            httpx.get(f"{url}/_control/config", timeout=1).raise_for_status()
            return
        except httpx.TransportError:
            time.sleep(0.1)
    raise RuntimeError("fake_strava did not start")


def _worker(settings: Settings, fake_url: str, *, burst: bool) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        **TEST_ENV,
        "DATABASE_URL": settings.database_url,
        "REDIS_URL": settings.redis_url,
        "STRAVA_API_BASE_URL": f"{fake_url}/api/v3",
        "STRAVA_OAUTH_BASE_URL": f"{fake_url}/oauth",
    }
    return subprocess.Popen(  # noqa: S603  (fixed args, our own interpreter)
        [sys.executable, "-m", "arq", "trainsync.worker.WorkerSettings", *(["--burst"] * burst)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


async def _run(sessionmaker: async_sessionmaker[AsyncSession]) -> SyncRun | None:
    async with sessionmaker() as session:
        return await session.scalar(select(SyncRun))


async def _count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(Activity)) or 0


async def _wait_for_pages(sessionmaker: async_sessionmaker[AsyncSession], pages: int) -> None:
    for _ in range(600):
        run = await _run(sessionmaker)
        if run is not None and run.pages >= pages:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"backfill did not reach {pages} pages")


async def test_sigkilled_worker_backfill_resumes_from_cursor(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    integration_settings: Settings,
    fake_strava_url: str,
) -> None:
    async with httpx.AsyncClient(base_url=fake_strava_url) as fake:
        token = await fake_strava_login(fake)
        athlete_id = await create_athlete(sessionmaker, token["athlete"]["id"])
        await SqlTokenStore(sessionmaker, TokenCipher.from_settings(integration_settings)).save(
            athlete_id,
            Tokens(
                token["access_token"],
                token["refresh_token"],
                datetime.fromtimestamp(token["expires_at"], UTC),
                "read,activity:read_all",
            ),
        )
        pool = create_arq_redis(integration_settings)
        try:
            await pool.enqueue_job("backfill", athlete_id, _job_id=backfill_job_id(athlete_id))
        finally:
            await pool.aclose()

        first = _worker(integration_settings, fake_strava_url, burst=False)
        try:
            await _wait_for_pages(sessionmaker, 2)
        finally:
            first.send_signal(signal.SIGKILL)
            first.wait(timeout=10)
        assert first.returncode == -signal.SIGKILL

        killed = await _run(sessionmaker)
        assert killed is not None
        assert killed.status == "running"  # no chance to pause: a hard kill
        assert killed.pages >= 2
        stored_before = await _count(sessionmaker)
        assert 0 < stored_before < 1000

        # What time does after a crash: arq's in-progress marker expires (job_timeout) and the
        # run's heartbeat goes stale. Both are wall-clock waits, so fast-forward them here.
        await redis.delete(f"{ARQ_IN_PROGRESS_PREFIX}{backfill_job_id(athlete_id)}")
        async with sessionmaker.begin() as session:
            await session.execute(
                update(SyncRun).values(updated_at=SyncRun.updated_at - STALE_AFTER * 2)
            )

        second = _worker(integration_settings, fake_strava_url, burst=True)
        output, _ = second.communicate(timeout=120)
        assert second.returncode == 0, output

        resumed = await _run(sessionmaker)
        assert resumed is not None
        assert (resumed.id, resumed.status) == (killed.id, "succeeded")
        assert await _count(sessionmaker) == 1000
        # Resumed from the cursor: the new worker fetched only the pages after the last
        # checkpoint (plus a final empty page if the history didn't end on a short one).
        new_pages = resumed.pages - killed.pages
        assert output.count('"event": "strava_call"') in (new_pages, new_pages + 1)
