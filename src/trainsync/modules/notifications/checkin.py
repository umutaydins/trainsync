"""The evening check-in prompt (P6.9, ADR 0020): an arq cron every 5 minutes that decides by
itself, for every user with a linked chat (ADR 0036), whether to send.

- At or after the user's check-in time on their local day (their time zone, DST-safe: the
  wall-clock time of each local date), the prompt goes out once, **only if no check-in exists
  for that day**.
- The user's reminder minutes after the prompt, still without a check-in, one reminder; then it
  stops until the next day.
- "Sent" bookkeeping is the `notifications` table (`checkin_prompt` / `checkin_reminder`, object
  id = local date as yyyymmdd): claimed before sending, released after a definite failure, kept
  after an unknown outcome. A restarted worker, or two cron runs, never send twice.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from arq.cron import cron
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
from trainsync.modules.chat.checkin import prompt
from trainsync.modules.checkin.repository import CheckinRepository
from trainsync.modules.coach.context import using_context
from trainsync.modules.coach.packs import Messages
from trainsync.modules.coach.voice import CoachVoice
from trainsync.modules.notifications.models import NotificationKind
from trainsync.modules.notifications.recipients import Recipient, recipients
from trainsync.modules.notifications.repository import NotificationRepository

log = get_logger(__name__)

CHECKIN_CTX_KEY = "trainsync_checkin"
CRON_MINUTES = set(range(0, 60, 5))


class Decision(StrEnum):
    NOTHING = "nothing"
    PROMPT = "prompt"
    REMINDER = "reminder"


def decide(
    now: datetime,
    zone: ZoneInfo,
    at: time,
    reminder_minutes: int,
    *,
    has_checkin: bool,
    prompt_sent_at: datetime | None,
    reminder_sent: bool,
) -> Decision:
    """What to send now for the local day `now` falls on (pure; the cron supplies the facts)."""
    due = local_moment(now.astimezone(zone).date(), at, zone)
    if has_checkin or now < due:
        return Decision.NOTHING
    if prompt_sent_at is None:
        return Decision.PROMPT
    if (
        reminder_minutes > 0
        and not reminder_sent
        and now >= prompt_sent_at + timedelta(minutes=reminder_minutes)
    ):
        return Decision.REMINDER
    return Decision.NOTHING


def day_key(day: date) -> int:
    """`notifications.object_id` of a local day: 2026-10-18 → 20261018."""
    return int(day.strftime("%Y%m%d"))


@dataclass(frozen=True, slots=True)
class CheckinDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    telegram: TelegramApi | None  # None: check-in off (no token, or CHECKIN_ENABLED=false)
    clock: Clock
    msg: Messages
    settings: Settings
    # Max profanity in savage (ADR 0032): the prompt gets an opener too. None: never.
    voice: CoachVoice | None = None


def build_checkin_deps(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    clock: Clock,
    sleep: Sleep,
    msg: Messages,
    voice: CoachVoice | None = None,
) -> CheckinDeps:
    telegram = None
    if settings.bot_enabled and settings.checkin_enabled is not False:
        telegram = TelegramApi(
            http,
            settings.telegram_bot_token,
            base_url=settings.telegram_api_base_url,
            sleep=sleep,
            max_attempts=2,  # the next cron run is the retry
        )
    return CheckinDeps(
        sessionmaker=sessionmaker,
        telegram=telegram,
        clock=clock,
        msg=msg,
        settings=settings,
        voice=voice,
    )


async def run_checkin(deps: CheckinDeps) -> dict[int, str]:
    """One scheduler tick for every linked user: user id → outcome."""
    if deps.telegram is None:
        return {}
    outcomes = {}
    for who in await recipients(deps.sessionmaker, deps.settings):
        with using_context(who.context()):
            outcomes[who.user_id] = await checkin_for(deps, who)
    return outcomes


async def checkin_for(deps: CheckinDeps, who: Recipient) -> str:
    """One user's tick. Outcome: disabled / nothing / duplicate / sent_prompt / sent_reminder /
    unknown / failed."""
    if deps.telegram is None or not who.settings.checkin_enabled:
        return "disabled"
    zone = who.settings.zone
    now = deps.clock()
    today = now.astimezone(zone).date()
    key = day_key(today)
    async with deps.sessionmaker() as session:
        has_checkin = await CheckinRepository(session, who.user_id).get(today) is not None
        notes = NotificationRepository(session, who.user_id)
        prompt_sent_at = await notes.sent_at(NotificationKind.CHECKIN_PROMPT, key)
        reminder_sent = await notes.sent_at(NotificationKind.CHECKIN_REMINDER, key) is not None
    decision = decide(
        now,
        zone,
        who.settings.checkin_time,
        who.settings.checkin_reminder_minutes,
        has_checkin=has_checkin,
        prompt_sent_at=prompt_sent_at,
        reminder_sent=reminder_sent,
    )
    if decision == Decision.NOTHING:
        return "nothing"
    kind = (
        NotificationKind.CHECKIN_PROMPT
        if decision == Decision.PROMPT
        else NotificationKind.CHECKIN_REMINDER
    )
    async with deps.sessionmaker.begin() as session:
        claimed = await NotificationRepository(session, who.user_id).claim(kind, key, now)
    if not claimed:
        return _count("duplicate")
    reply = prompt(deps.msg, today, reminder=decision == Decision.REMINDER)
    text = await deps.voice.decorate(reply.text) if deps.voice else reply.text
    try:
        await deps.telegram.send_message(who.chat_id, text, reply.keyboard)
    except TelegramDeliveryUnknownError as exc:
        log.warning("checkin_delivery_unknown", day=today.isoformat(), error=str(exc))
        return _count("unknown")  # keep the claim: better no prompt than two
    except (TelegramError, TelegramRetryAfterError, TelegramUnavailableError) as exc:
        async with deps.sessionmaker.begin() as session:
            await NotificationRepository(session, who.user_id).release(kind, key)
        log.warning("checkin_send_failed", day=today.isoformat(), error=str(exc))
        return _count("failed")  # the next tick tries again
    log.info("checkin_sent", user_id=who.user_id, day=today.isoformat(), kind=kind.value)
    return _count(f"sent_{decision.value}")


def _count(outcome: str) -> str:
    NOTIFICATIONS.labels("telegram", f"checkin_{outcome}").inc()
    return outcome


async def checkin_tick(ctx: dict[str, Any]) -> dict[int, str]:
    deps: CheckinDeps = ctx[CHECKIN_CTX_KEY]
    return await run_checkin(deps)


checkin_cron = cron(checkin_tick, name="checkin_tick", minute=CRON_MINUTES, run_at_startup=True)
