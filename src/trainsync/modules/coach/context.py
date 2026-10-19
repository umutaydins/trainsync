"""One user's context for the current task (ADR 0036): voice (tone, language, intensity,
profanity, emergency number) and clock (time zone, reminder time, sugar limit) come from their
settings. The bot enters it per update, the worker per send; nothing outside the block sees it.
"""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from trainsync.core.settings import BotLang, BotProfanity, BotTone
from trainsync.modules.coach.mode import using_intensity, using_profanity, using_user
from trainsync.modules.coach.packs import CURRENT_EMERGENCY, using_lang, using_tone

CURRENT_ZONE: ContextVar[ZoneInfo | None] = ContextVar("trainsync_zone", default=None)
CURRENT_REMINDER: ContextVar[time | None] = ContextVar("trainsync_reminder", default=None)
CURRENT_SUGAR_LIMIT: ContextVar[float | None] = ContextVar("trainsync_sugar_limit", default=None)


@dataclass(frozen=True, slots=True)
class UserContext:
    """None everywhere = the configured defaults (an unlinked chat, a test)."""

    user_id: int | None = None
    tone: BotTone | None = None
    lang: BotLang | None = None
    savage: bool | None = None
    profanity: BotProfanity | None = None
    emergency_number: str | None = None
    timezone: str | None = None
    workout_reminder_time: time | None = None
    sugar_limit_g: float | None = None


def current_zone(default: ZoneInfo) -> ZoneInfo:
    return CURRENT_ZONE.get() or default


def current_reminder(default: time) -> time:
    return CURRENT_REMINDER.get() or default


def current_sugar_limit(default: float) -> float:
    return CURRENT_SUGAR_LIMIT.get() or default


@contextmanager
def _var[T](var: ContextVar[T], value: T) -> Iterator[None]:
    token = var.set(value)
    try:
        yield
    finally:
        var.reset(token)


@contextmanager
def using_context(context: UserContext) -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(using_user(context.user_id))
        stack.enter_context(using_tone(context.tone))
        stack.enter_context(using_lang(context.lang))
        stack.enter_context(using_intensity(context.savage))
        stack.enter_context(using_profanity(context.profanity))
        stack.enter_context(_var(CURRENT_EMERGENCY, context.emergency_number))
        zone = ZoneInfo(context.timezone) if context.timezone else None
        stack.enter_context(_var(CURRENT_ZONE, zone))
        stack.enter_context(_var(CURRENT_REMINDER, context.workout_reminder_time))
        stack.enter_context(_var(CURRENT_SUGAR_LIMIT, context.sugar_limit_g))
        yield
