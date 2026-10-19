"""Weekly and monthly progress digests (P8.11, ADR 0038): an arq cron every 5 minutes.

On Monday from `STATS_DIGEST_TIME` (the user's local time) the user gets last week's summary; on
the 1st, last month's. Quiet hours hold it until they end (the same local day). Each digest is
claimed once in `notifications` (object id: the first day of the period as yyyymmdd) before it is
built, so two cron runs or a restart never send it twice; a period with nothing in it is claimed
and not sent. Delivery errors follow the check-in prompt: released after a definite failure, kept
after an unknown outcome.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

import httpx
from arq.cron import cron
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock, Sleep
from trainsync.core.localtime import local_moment
from trainsync.core.logging import get_logger
from trainsync.core.metrics import NOTIFICATIONS
from trainsync.core.settings import Settings
from trainsync.integrations.telegram.client import (
    TelegramApi,
    TelegramDeliveryUnknownError,
    TelegramError,
    TelegramRetryAfterError,
    TelegramUnavailableError,
)
from trainsync.modules.auth.models import UserRole
from trainsync.modules.auth.service import Principal
from trainsync.modules.chat.progress import progress_message
from trainsync.modules.coach.context import using_context
from trainsync.modules.coach.packs import Key, Messages
from trainsync.modules.coach.schedule import is_quiet
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.notifications.checkin import day_key
from trainsync.modules.notifications.models import NotificationKind
from trainsync.modules.notifications.recipients import Recipient, recipients
from trainsync.modules.notifications.repository import NotificationRepository
from trainsync.modules.stats.periods import Period, add_months
from trainsync.modules.stats.totals import StatsSummary
from trainsync.modules.stats.views import summary_of

log = get_logger(__name__)

DIGEST_CTX_KEY = "trainsync_digest"
CRON_MINUTES = set(range(0, 60, 5))
MONDAY = 0
FIRST_OF_MONTH = 1
WEEK = timedelta(7)


@dataclass(frozen=True, slots=True)
class Due:
    kind: NotificationKind
    period: Period
    title: Key
    object_id: int


def due(now: datetime, who: Recipient, at: time) -> list[Due]:
    """The digests the user's local day owes from `STATS_DIGEST_TIME` on (pure)."""
    zone = who.settings.zone
    today = now.astimezone(zone).date()
    if now < local_moment(today, at, zone):
        return []
    owed: list[Due] = []
    if today.weekday() == MONDAY:
        last_monday = today - WEEK
        week_id = day_key(last_monday)
        owed.append(
            Due(NotificationKind.STATS_DIGEST_WEEK, Period.LAST_WEEK, Key.DIGEST_WEEK, week_id)
        )
    if today.day == FIRST_OF_MONTH:
        owed.append(
            Due(
                NotificationKind.STATS_DIGEST_MONTH,
                Period.LAST_MONTH,
                Key.DIGEST_MONTH,
                day_key(add_months(today.replace(day=1), -1)),
            )
        )
    return owed


def has_news(summary: StatsSummary) -> bool:
    """Anything trained, logged or checked in during the period."""
    return bool(
        summary.endurance.totals.count.value
        or summary.strength.sessions.value
        or summary.nutrition.logged_days.value
        or summary.consistency.checkin_rate.value
    )


@dataclass(frozen=True, slots=True)
class DigestDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    telegram: TelegramApi | None  # None: digests off (no token, or STATS_DIGEST_ENABLED=false)
    clock: Clock
    msg: Messages
    settings: Settings
    redis: Redis
    voice: CoachVoice | None = None


def build_digest_deps(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    redis: Redis,
    clock: Clock,
    sleep: Sleep,
    msg: Messages,
    voice: CoachVoice | None = None,
) -> DigestDeps:
    telegram = None
    if settings.bot_enabled and settings.stats_digest_enabled is not False:
        telegram = TelegramApi(
            http,
            settings.telegram_bot_token,
            base_url=settings.telegram_api_base_url,
            sleep=sleep,
            max_attempts=2,  # the next cron run is the retry
        )
    return DigestDeps(sessionmaker, telegram, clock, msg, settings, redis, voice)


async def run_digests(deps: DigestDeps) -> dict[int, list[str]]:
    """One tick for every linked user: user id → the outcome of each digest due."""
    if deps.telegram is None:
        return {}
    outcomes: dict[int, list[str]] = {}
    for who in await recipients(deps.sessionmaker, deps.settings):
        with using_context(who.context()):
            outcomes[who.user_id] = await digests_for(deps, who)
    return outcomes


async def digests_for(deps: DigestDeps, who: Recipient) -> list[str]:
    """Outcomes: disabled / quiet / duplicate / empty / sent / unknown / failed."""
    if not who.settings.stats_digest_enabled:
        return ["disabled"]
    now = deps.clock()
    owed = due(now, who, deps.settings.stats_digest_time)
    if owed and is_quiet(now, who.settings.quiet_window, who.settings.zone):
        return [_count("quiet") for _ in owed]
    telegram = deps.telegram
    if telegram is None:
        return ["disabled"]
    return [await _one(deps, telegram, who, digest, now) for digest in owed]


async def _one(
    deps: DigestDeps, telegram: TelegramApi, who: Recipient, digest: Due, now: datetime
) -> str:
    async with deps.sessionmaker.begin() as session:
        notes = NotificationRepository(session, who.user_id)
        if not await notes.claim(digest.kind, digest.object_id, now):
            return _count("duplicate")
    principal = Principal(who.user_id, UserRole.USER, who.settings.timezone)
    async with deps.sessionmaker() as session:
        summary = await summary_of(
            session, principal, now, deps.settings, deps.redis, digest.period
        )
    if not has_news(summary):
        return _count("empty")  # keep the claim: nothing to say about this period
    text = await progress_message(summary, digest.title, deps.msg, deps.voice)
    try:
        await telegram.send_message(who.chat_id, text)
    except TelegramDeliveryUnknownError as exc:
        log.warning("digest_delivery_unknown", kind=digest.kind.value, error=str(exc))
        return _count("unknown")
    except (TelegramError, TelegramRetryAfterError, TelegramUnavailableError) as exc:
        async with deps.sessionmaker.begin() as session:
            await NotificationRepository(session, who.user_id).release(
                digest.kind, digest.object_id
            )
        log.warning("digest_send_failed", kind=digest.kind.value, error=str(exc))
        return _count("failed")
    log.info("digest_sent", user_id=who.user_id, kind=digest.kind.value)
    return _count("sent")


def _count(outcome: str) -> str:
    NOTIFICATIONS.labels("telegram", f"digest_{outcome}").inc()
    return outcome


async def digest_tick(ctx: dict[str, Any]) -> dict[int, list[str]]:
    deps: DigestDeps = ctx[DIGEST_CTX_KEY]
    return await run_digests(deps)


digest_cron = cron(digest_tick, name="digest_tick", minute=CRON_MINUTES, run_at_startup=True)
