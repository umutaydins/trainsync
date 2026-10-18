"""`notify_new_activity`: one message per new activity, at most once (ADR 0012).

Enqueued by webhook processing after an `activity create` event was upserted (job id
`notify:{strava_activity_id}`). Backfill and incremental sync never enqueue it: they import
history, which is not news.

Idempotency: claim the `(new_activity, id)` row in `notifications` (insert, `ON CONFLICT DO
NOTHING`), commit, then send. A definite failure releases the claim and arq retries the job with
backoff (at most `NOTIFY_MAX_TRIES` tries). An unknown outcome (timeout after the request went
out) keeps the claim: better one missed message than two.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
from arq import Retry
from arq.worker import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.api.activities import ActivityOut
from trainsync.bot.formatting import format_new_activity
from trainsync.bot.telegram import TelegramApi
from trainsync.core.clock import Clock, Sleep
from trainsync.core.logging import get_logger
from trainsync.core.metrics import NOTIFICATIONS
from trainsync.core.settings import Settings
from trainsync.db.models import NotificationKind
from trainsync.db.repositories.notifications import NotificationRepository
from trainsync.db.repositories.reads import ReadRepository
from trainsync.notify.base import DeliveryUnknownError, Notifier, NotifyFailedError, NullNotifier
from trainsync.notify.telegram import TelegramNotifier
from trainsync.sync.context import job_log_context

log = get_logger(__name__)

NOTIFY_CTX_KEY = "trainsync_notify"
NOTIFY_MAX_TRIES = 5
RETRY_BASE = timedelta(seconds=10)


@dataclass(frozen=True, slots=True)
class NotifyDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    notifier: Notifier
    chat_ref: str | None
    dashboard_url: str
    clock: Clock


def build_notifier(
    settings: Settings, http: httpx.AsyncClient, sleep: Sleep
) -> tuple[Notifier, str | None]:
    """Telegram when a token and a target chat are configured, else the NullNotifier."""
    chat_id = settings.notify_chat_id()
    if not settings.bot_enabled or chat_id is None:
        return NullNotifier(), None
    api = TelegramApi(
        http,
        settings.telegram_bot_token,
        base_url=settings.telegram_api_base_url,
        sleep=sleep,
        max_attempts=2,  # one quick in-process retry; arq retries with backoff after that
    )
    return TelegramNotifier(api), str(chat_id)


def retry_delay(job_try: int) -> timedelta:
    """10 s, 30 s, 90 s, 270 s after try 1, 2, 3, 4."""
    return RETRY_BASE * int(3 ** (job_try - 1))


async def send_new_activity(deps: NotifyDeps, strava_activity_id: int) -> str:
    """Outcome: sent / duplicate / skipped (gone) / disabled / unknown. Raises
    `NotifyFailedError` after releasing the claim."""
    if deps.chat_ref is None:
        return _count(deps, "disabled")
    async with deps.sessionmaker() as session:
        reads = ReadRepository(session)
        row = await reads.activity(strava_activity_id, await reads.active_athlete_ids())
        if row is None:
            return _count(deps, "skipped")  # deleted, or the athlete left, before we got here
        text = format_new_activity(ActivityOut.from_row(row, include_raw=False), deps.dashboard_url)

    kind = NotificationKind.NEW_ACTIVITY
    async with deps.sessionmaker.begin() as session:
        claimed = await NotificationRepository(session).claim(
            kind, strava_activity_id, deps.clock()
        )
    if not claimed:
        return _count(deps, "duplicate")
    try:
        await deps.notifier.send(deps.chat_ref, text)
    except DeliveryUnknownError as exc:
        log.warning("notification_delivery_unknown", activity_id=strava_activity_id, error=str(exc))
        return _count(deps, "unknown")
    except Exception:
        # Definitely not delivered (or a bug): release, so a retry can claim it again.
        # Cancellation is not caught: the claim stays, like an unknown outcome.
        async with deps.sessionmaker.begin() as session:
            await NotificationRepository(session).release(kind, strava_activity_id)
        _count(deps, "failed")
        raise
    log.info("notification_sent", activity_id=strava_activity_id, channel=deps.notifier.channel)
    return _count(deps, "sent")


def _count(deps: NotifyDeps, outcome: str) -> str:
    NOTIFICATIONS.labels(deps.notifier.channel, outcome).inc()
    return outcome


async def notify_new_activity(ctx: dict[str, Any], strava_activity_id: int) -> str:
    with job_log_context(ctx, "notify_new_activity", activity_id=strava_activity_id):
        deps: NotifyDeps = ctx[NOTIFY_CTX_KEY]
        job_try: int = ctx.get("job_try") or 1
        try:
            return await send_new_activity(deps, strava_activity_id)
        except NotifyFailedError as exc:
            if job_try >= NOTIFY_MAX_TRIES:
                log.error("notification_gave_up", activity_id=strava_activity_id, tries=job_try)
                return "gave_up"
            delay = retry_delay(job_try)
            if exc.retry_after is not None:
                delay = max(delay, timedelta(seconds=exc.retry_after))
            log.warning("notification_retry", error=str(exc), job_try=job_try, defer=delay)
            raise Retry(defer=delay) from None


notify_new_activity_job = func(
    notify_new_activity, name="notify_new_activity", max_tries=NOTIFY_MAX_TRIES
)
