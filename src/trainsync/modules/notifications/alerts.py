"""Stack-internal alerts (P7.8, ADR 0027): an arq cron every 5 minutes looks at the stack and
sends one Telegram message when a condition starts and one when it clears.

Conditions (thresholds in Settings, `ALERT_*`):

- `circuit_open`: the Strava circuit breaker has not been closed for `ALERT_CIRCUIT_OPEN_MINUTES`;
- `dead_letters`: at least one webhook event failed `MAX_ATTEMPTS` times and is no longer retried;
- `backup_stale`: the newest backup in `BACKUP_DIR` is older than `ALERT_BACKUP_MAX_AGE_HOURS`
  (not checked while `BACKUP_DIR` is empty);
- `sync_stale`: no successful sync for `ALERT_SYNC_STALE_HOURS` while an athlete is connected.

State: one Redis key per condition, `alert:{condition}` = `{"bad_since": …, "alerted": …}`, no
expiry (Redis runs with appendonly in production), so a restarted worker neither repeats an
alert nor forgets to send the recovery. A definite send failure keeps the old state (the next
tick tries again); an unknown outcome counts as sent (better a missed message than two).
Off, without touching the state, while no Telegram target is configured.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from arq.cron import cron
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.metrics import NOTIFICATIONS
from trainsync.core.settings import BotLang, Settings
from trainsync.integrations.notifier import DeliveryUnknownError, Notifier, NotifyFailedError
from trainsync.integrations.strava.breaker_status import overall_state, read_breakers
from trainsync.modules.notifications.alert_conditions import (
    Action,
    AlertState,
    Condition,
    Detail,
    Facts,
    Observation,
    Thresholds,
    newest_backup,
    observe,
    step,
)
from trainsync.modules.notifications.alert_texts import AFTER, DETAILS, HEADLINES, message
from trainsync.modules.notifications.recipients import chat_lang
from trainsync.modules.sync.status_repository import system_freshness
from trainsync.modules.sync.webhook_repository import WebhookEventRepository

__all__ = [
    "AFTER",
    "ALERTS_CTX_KEY",
    "DETAILS",
    "HEADLINES",
    "Action",
    "AlertDeps",
    "AlertState",
    "Condition",
    "Detail",
    "Facts",
    "Observation",
    "RedisAlertStore",
    "StackFacts",
    "Thresholds",
    "alerts_cron",
    "alerts_tick",
    "build_alert_deps",
    "message",
    "newest_backup",
    "observe",
    "run_alerts",
    "step",
]

log = get_logger(__name__)

ALERTS_CTX_KEY = "trainsync_alerts"
CRON_MINUTES = set(range(0, 60, 5))
KEY_PREFIX = "alert:"


class FactSource(Protocol):
    async def collect(self, now: datetime) -> Facts: ...


class AlertStore(Protocol):
    async def load(self, condition: Condition) -> AlertState: ...

    async def save(self, condition: Condition, state: AlertState) -> None: ...


class StackFacts:
    """Facts from Postgres, the breaker keys in Redis and the mounted backup folder."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        backup_dir: Path | None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._redis = redis
        self._backup_dir = backup_dir

    async def collect(self, now: datetime) -> Facts:
        async with self._sessionmaker() as session:
            dead = await WebhookEventRepository(session).count_dead()
            athletes_active, last = await system_freshness(session)
        reports = await read_breakers(self._redis)
        backup = None
        if self._backup_dir is not None:
            backup = await asyncio.to_thread(newest_backup, self._backup_dir)
        return Facts(
            circuit=overall_state(reports, now) if reports else None,
            dead_letters=dead,
            athletes_active=athletes_active,
            last_synced_at=last,
            backup_dir=str(self._backup_dir) if self._backup_dir is not None else None,
            newest_backup=backup,
        )


class RedisAlertStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def load(self, condition: Condition) -> AlertState:
        raw: str | bytes | None = await self._redis.get(f"{KEY_PREFIX}{condition.value}")
        return AlertState.from_json(raw)

    async def save(self, condition: Condition, state: AlertState) -> None:
        await self._redis.set(f"{KEY_PREFIX}{condition.value}", state.to_json())


@dataclass(frozen=True, slots=True)
class AlertDeps:
    facts: FactSource
    store: AlertStore
    notifier: Notifier
    chat_ref: str | None  # None: alerts off (no Telegram target)
    clock: Clock
    thresholds: Thresholds = field(default_factory=Thresholds)
    # The chat's stored language at send time (ADR 0031); None: English.
    language: Callable[[str], Awaitable[BotLang | None]] | None = None


def build_alert_deps(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    notifier: Notifier,
    chat_ref: str | None,
    clock: Clock,
) -> AlertDeps:
    backup_dir = Path(settings.backup_dir) if settings.backup_dir.strip() else None
    return AlertDeps(
        facts=StackFacts(sessionmaker, redis, backup_dir),
        store=RedisAlertStore(redis),
        notifier=notifier,
        chat_ref=chat_ref,
        clock=clock,
        thresholds=Thresholds.from_settings(settings),
        language=lambda chat: chat_lang(sessionmaker, settings, chat),
    )


async def run_alerts(deps: AlertDeps) -> dict[Condition, str]:
    """One tick. Outcome per condition: quiet / sent_fire / sent_resolve / unknown / failed;
    `{}` when alerts are off."""
    chat = deps.chat_ref
    if chat is None:
        return {}
    now = deps.clock()
    facts = await deps.facts.collect(now)
    outcomes: dict[Condition, str] = {}
    for condition, observation in observe(facts, now, deps.thresholds).items():
        old = await deps.store.load(condition)
        new, action = step(old, observation.bad, now, observation.grace)
        if action is Action.NONE:
            if new != old:
                await deps.store.save(condition, new)
            outcomes[condition] = "quiet"
            continue
        outcomes[condition] = await _send(deps, chat, condition, action, observation, old, new, now)
    return outcomes


async def _send(
    deps: AlertDeps,
    chat: str,
    condition: Condition,
    action: Action,
    observation: Observation,
    old: AlertState,
    new: AlertState,
    now: datetime,
) -> str:
    try:
        lang = await deps.language(chat) if deps.language is not None else None
        await deps.notifier.send(chat, message(action, observation, old, now, lang or "en"))
    except DeliveryUnknownError as exc:
        log.warning("alert_delivery_unknown", condition=condition.value, error=str(exc))
        await deps.store.save(condition, new)
        return _count(deps, "unknown")
    except NotifyFailedError as exc:
        # Not delivered: keep the old state so the next tick sends it again (for a new
        # condition, keep when it started).
        retry = AlertState(new.bad_since, alerted=False) if action is Action.FIRE else old
        await deps.store.save(condition, retry)
        log.warning("alert_send_failed", condition=condition.value, error=str(exc))
        return _count(deps, "failed")
    await deps.store.save(condition, new)
    log.info("alert_sent", condition=condition.value, action=action.value)
    return _count(deps, f"sent_{action.value}")


def _count(deps: AlertDeps, outcome: str) -> str:
    NOTIFICATIONS.labels(deps.notifier.channel, f"alert_{outcome}").inc()
    return outcome


async def alerts_tick(ctx: dict[str, Any]) -> dict[str, str]:
    deps: AlertDeps = ctx[ALERTS_CTX_KEY]
    return {condition.value: outcome for condition, outcome in (await run_alerts(deps)).items()}


alerts_cron = cron(alerts_tick, name="stack_alerts", minute=CRON_MINUTES)
