import os
import subprocess
import sys
from pathlib import Path

from arq import create_pool
from arq.worker import Worker

from tests.conftest import TEST_ENV
from trainsync.core.jobs import redis_settings
from trainsync.core.settings import Settings
from trainsync.entrypoints.worker.settings import WorkerSettings
from trainsync.modules.sync.context import worker_context

REPO_ROOT = Path(__file__).resolve().parents[2]


async def test_worker_lifecycle_creates_and_closes_resources(
    integration_settings: Settings,
) -> None:
    worker = Worker(
        functions=WorkerSettings.functions,
        on_startup=WorkerSettings.on_startup,
        on_shutdown=WorkerSettings.on_shutdown,
        redis_settings=redis_settings(integration_settings),
        ctx={"settings": integration_settings},
        burst=True,
        poll_delay=0.01,
        handle_signals=False,
    )
    pool = await create_pool(redis_settings(integration_settings))
    await pool.enqueue_job("ping")
    await pool.aclose()
    try:
        await worker.async_run()
        context = worker_context(worker.ctx)
        assert worker.jobs_complete == 1
        assert context.strava is not None
    finally:
        await worker.close()
    assert context.engine.pool.checkedout() == 0
    http = context.strava._http
    assert http.is_closed


def test_arq_cli_starts_and_exits_cleanly(integration_settings: Settings) -> None:
    env = {
        **os.environ,
        **TEST_ENV,
        "DATABASE_URL": integration_settings.database_url,
        "REDIS_URL": integration_settings.redis_url,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "arq",
            "trainsync.entrypoints.worker.settings.WorkerSettings",
            "--burst",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "worker_startup" in output
    assert "worker_shutdown" in output
