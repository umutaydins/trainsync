"""Helpers for the new-activity notification tests: a Telegram-backed `NotifyDeps` (Telegram
faked with respx, see tests/support/telegram.py) and a stand-in for the arq worker."""

from typing import Any

import httpx
from arq import Retry
from arq.connections import ArqRedis
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.messages import NEUTRAL_EN
from tests.support.telegram import BOT_TOKEN, TELEGRAM, SleepRecorder
from trainsync.bot.telegram import TelegramApi
from trainsync.core.clock import utc_now
from trainsync.db.models import Notification
from trainsync.notify.jobs import NOTIFY_CTX_KEY, NotifyDeps, notify_new_activity
from trainsync.notify.telegram import TelegramNotifier

CHAT_ID = 4242
DASHBOARD = "https://dash.test"


def telegram_notify_deps(
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    sleep: SleepRecorder | None = None,
) -> NotifyDeps:
    api = TelegramApi(
        http,
        SecretStr(BOT_TOKEN),
        base_url=TELEGRAM,
        sleep=sleep or SleepRecorder(),
        max_attempts=2,
    )
    return NotifyDeps(
        sessionmaker, TelegramNotifier(api), str(CHAT_ID), DASHBOARD, utc_now, NEUTRAL_EN
    )


async def queued_notify_jobs(pool: ArqRedis) -> list[tuple[str, int]]:
    """(job id, activity id) of every queued `notify_new_activity` job."""
    jobs = await pool.queued_jobs()
    return sorted(
        (job.job_id or "", int(job.args[0]))
        for job in jobs
        if job.function == "notify_new_activity"
    )


async def run_like_arq(
    deps: NotifyDeps, activity_id: int, *, max_tries: int
) -> tuple[str, list[Retry]]:
    """Run the job the way arq does: again after every `Retry`, with `job_try` counting up, and
    without waiting for the deferral (the test checks the requested delays instead)."""
    retries: list[Retry] = []
    for job_try in range(1, max_tries + 1):
        ctx: dict[str, Any] = {
            NOTIFY_CTX_KEY: deps,
            "job_try": job_try,
            "job_id": f"notify:{activity_id}",
        }
        try:
            return await notify_new_activity(ctx, activity_id), retries
        except Retry as retry:
            retries.append(retry)
    return "max_tries", retries


async def notification_rows(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(Notification)) or 0
