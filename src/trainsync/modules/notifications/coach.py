"""Timed coach messages (P6.11, ADR 0030), sent by the worker to each user's linked chat
(ADR 0036).

- `coach_tick` (cron, every minute), per user: today's scheduled program day (weekday, start
  time; the user's local time) gets a reminder 30 min before, one at the start, nudges at
  +30 and +90 min and a "missed" message at +180 min, each only while no workout was started
  that local day and only within `GRACE` of its moment (never late).
- Jobs enqueued by the API: `coach_workout_started`, `coach_set_logged` (under target once per
  exercise; schedules `coach_rest_over` for the end of the planned rest), `coach_rest_over`
  (only if no newer set was logged and planned sets remain), `coach_workout_finished` (summary
  and verdict: PRs praised, misses roasted).

Every message claims a `notifications` row first (kind + local date / workout / set id), is
released after a definite send failure and kept after an unknown outcome, so retries, restarts
and duplicate jobs never repeat one. Nothing is sent in the user's quiet hours; such a message
is dropped, not delayed.
"""

from typing import Any

import httpx
from arq.cron import cron
from arq.worker import func
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock, Sleep
from trainsync.core.settings import Settings
from trainsync.integrations.telegram.client import TelegramApi
from trainsync.modules.coach.packs import Messages
from trainsync.modules.coach.voice import build_voice
from trainsync.modules.notifications.coach_events import (
    rest_over,
    set_logged,
    under_target_key,
    workout_finished,
    workout_started,
)
from trainsync.modules.notifications.coach_reminders import reminders_for, run_reminders
from trainsync.modules.notifications.coach_send import CoachDeps, send
from trainsync.modules.training.workout_detail import progression_rules

__all__ = [
    "COACH_CTX_KEY",
    "COACH_JOBS",
    "CoachDeps",
    "build_coach_deps",
    "coach_cron",
    "reminders_for",
    "rest_over",
    "run_reminders",
    "send",
    "set_logged",
    "under_target_key",
    "workout_finished",
    "workout_started",
]

COACH_CTX_KEY = "trainsync_coach"
# Telegram attempts per coach message: a reminder that cannot go out soon is not worth more.
SEND_ATTEMPTS = 2


def build_coach_deps(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    redis: Redis,
    clock: Clock,
    sleep: Sleep,
    msg: Messages,
) -> CoachDeps:
    telegram = None
    if settings.bot_enabled and settings.coach_messages_enabled is not False:
        telegram = TelegramApi(
            http,
            settings.telegram_bot_token,
            base_url=settings.telegram_api_base_url,
            sleep=sleep,
            max_attempts=SEND_ATTEMPTS,
        )
    return CoachDeps(
        sessionmaker=sessionmaker,
        telegram=telegram,
        clock=clock,
        voice=build_voice(settings, redis, msg),
        msg=msg,
        rules=progression_rules(settings),
        settings=settings,
    )


async def coach_tick(ctx: dict[str, Any]) -> dict[int, str]:
    deps: CoachDeps = ctx[COACH_CTX_KEY]
    return await run_reminders(deps)


coach_cron = cron(coach_tick, name="coach_tick", minute=set(range(60)), run_at_startup=True)


async def coach_workout_started(ctx: dict[str, Any], workout_id: int) -> str:
    return await workout_started(ctx[COACH_CTX_KEY], workout_id)


async def coach_set_logged(ctx: dict[str, Any], set_id: int) -> str:
    return await set_logged(ctx[COACH_CTX_KEY], set_id, ctx.get("redis"))


async def coach_rest_over(ctx: dict[str, Any], set_id: int) -> str:
    return await rest_over(ctx[COACH_CTX_KEY], set_id)


async def coach_workout_finished(ctx: dict[str, Any], workout_id: int) -> str:
    return await workout_finished(ctx[COACH_CTX_KEY], workout_id)


COACH_JOBS = [
    func(coach_workout_started, name="coach_workout_started", max_tries=3),
    func(coach_set_logged, name="coach_set_logged", max_tries=3),
    func(coach_rest_over, name="coach_rest_over", max_tries=3),
    func(coach_workout_finished, name="coach_workout_finished", max_tries=3),
]
