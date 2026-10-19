"""Sending one timed coach message: claim the `notifications` row, respect quiet hours, send,
release after a definite failure (ADR 0030)."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
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
from trainsync.modules.coach.packs import Messages
from trainsync.modules.coach.schedule import is_quiet
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.notifications.models import NotificationKind
from trainsync.modules.notifications.recipients import Recipient
from trainsync.modules.notifications.repository import NotificationRepository
from trainsync.modules.training.progression import Rules

log = get_logger("trainsync.modules.notifications.coach")


@dataclass(frozen=True)
class CoachDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    telegram: TelegramApi | None  # None: timed coach messages off
    clock: Clock
    voice: CoachVoice
    msg: Messages
    rules: Rules
    settings: Settings


async def send(
    deps: CoachDeps, who: Recipient, kind: NotificationKind, object_id: int, text: str
) -> str:
    """Claim, send, and release after a definite failure. Outcome: disabled / quiet / duplicate
    / sent / unknown / failed."""
    if deps.telegram is None:
        return "disabled"
    now = deps.clock()
    if is_quiet(now, who.settings.quiet_window, who.settings.zone):
        log.info("coach_quiet_hours", user_id=who.user_id, kind=kind.value)
        return _count("quiet")
    async with deps.sessionmaker.begin() as session:
        claimed = await NotificationRepository(session, who.user_id).claim(kind, object_id, now)
    if not claimed:
        return _count("duplicate")
    text = await deps.voice.decorate(text)  # max profanity: every message swears (ADR 0032)
    try:
        await deps.telegram.send_message(who.chat_id, text)
    except TelegramDeliveryUnknownError as exc:
        log.warning("coach_delivery_unknown", kind=kind.value, error=str(exc))
        return _count("unknown")
    except (TelegramError, TelegramRetryAfterError, TelegramUnavailableError) as exc:
        async with deps.sessionmaker.begin() as session:
            await NotificationRepository(session, who.user_id).release(kind, object_id)
        log.warning("coach_send_failed", kind=kind.value, error=str(exc))
        return _count("failed")
    log.info("coach_sent", kind=kind.value, object_id=object_id)
    return _count("sent")


def _count(outcome: str) -> str:
    NOTIFICATIONS.labels("telegram", f"coach_{outcome}").inc()
    return outcome
