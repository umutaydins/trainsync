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

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from arq.cron import cron
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.core.metrics import NOTIFICATIONS
from trainsync.core.settings import BotLang, Settings
from trainsync.db.repositories.reads import ReadRepository
from trainsync.db.repositories.webhook_events import MAX_ATTEMPTS, WebhookEventRepository
from trainsync.notify.base import DeliveryUnknownError, Notifier, NotifyFailedError
from trainsync.notify.language import stored_lang
from trainsync.ops.retention import Backup, parse_name
from trainsync.strava.breaker import BreakerState
from trainsync.strava.breaker_status import overall_state, read_breakers

log = get_logger(__name__)

ALERTS_CTX_KEY = "trainsync_alerts"
CRON_MINUTES = set(range(0, 60, 5))
KEY_PREFIX = "alert:"


class Condition(StrEnum):
    CIRCUIT_OPEN = "circuit_open"
    DEAD_LETTERS = "dead_letters"
    BACKUP_STALE = "backup_stale"
    SYNC_STALE = "sync_stale"


class Action(StrEnum):
    NONE = "none"
    FIRE = "fire"
    RESOLVE = "resolve"


@dataclass(frozen=True, slots=True)
class AlertState:
    bad_since: datetime | None = None  # first tick the condition was seen bad
    alerted: bool = False  # the "started" message went out

    def to_json(self) -> str:
        since = self.bad_since.isoformat() if self.bad_since else None
        return json.dumps({"bad_since": since, "alerted": self.alerted})

    @classmethod
    def from_json(cls, raw: str | bytes | None) -> "AlertState":
        if raw is None:
            return cls()
        try:
            data = json.loads(raw)
            since = data.get("bad_since")
            return cls(datetime.fromisoformat(since) if since else None, bool(data["alerted"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            return cls()


@dataclass(frozen=True, slots=True)
class Observation:
    bad: bool | None  # None: cannot tell this tick, the state stays as it is
    detail: "Detail"
    fields: Mapping[str, object] = field(default_factory=dict)
    grace: timedelta = timedelta(0)  # bad for this long before the alert fires


def step(
    state: AlertState, bad: bool | None, now: datetime, grace: timedelta = timedelta(0)
) -> tuple[AlertState, Action]:
    """The next state and what to send for one observation (pure)."""
    if bad is None:
        return state, Action.NONE
    if not bad:
        return AlertState(), Action.RESOLVE if state.alerted else Action.NONE
    since = state.bad_since or now
    if not state.alerted and now - since >= grace:
        return AlertState(since, alerted=True), Action.FIRE
    return AlertState(since, state.alerted), Action.NONE


@dataclass(frozen=True, slots=True)
class Thresholds:
    circuit_open: timedelta = timedelta(minutes=30)
    backup_max_age: timedelta = timedelta(hours=36)
    sync_stale: timedelta = timedelta(hours=2)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Thresholds":
        return cls(
            circuit_open=timedelta(minutes=settings.alert_circuit_open_minutes),
            backup_max_age=timedelta(hours=settings.alert_backup_max_age_hours),
            sync_stale=timedelta(hours=settings.alert_sync_stale_hours),
        )


@dataclass(frozen=True, slots=True)
class Facts:
    circuit: BreakerState | None  # worst state across processes; None = nobody reported
    dead_letters: int
    athletes_active: bool
    last_synced_at: datetime | None
    backup_dir: str | None = None  # None: backups are not checked
    newest_backup: Backup | None = None


class Detail(StrEnum):
    CIRCUIT_UNKNOWN = "circuit_unknown"
    CIRCUIT_CLOSED = "circuit_closed"
    CIRCUIT_OPEN = "circuit_open"
    DEAD_LETTERS = "dead_letters"
    DEAD_LETTERS_NONE = "dead_letters_none"
    NO_ATHLETE = "no_athlete"
    NEVER_SYNCED = "never_synced"
    SYNC_STALE = "sync_stale"
    SYNC_OK = "sync_ok"
    NO_BACKUP = "no_backup"
    BACKUP_STALE = "backup_stale"
    BACKUP_OK = "backup_ok"


# The chat's language (`/lang`, ADR 0031); tone-free, like the neutral layer.
DETAILS: Mapping[BotLang, Mapping[Detail, str]] = {
    "en": {
        Detail.CIRCUIT_UNKNOWN: "no circuit breaker state reported",
        Detail.CIRCUIT_CLOSED: "Strava circuit breaker is closed again",
        Detail.CIRCUIT_OPEN: "Strava circuit breaker {state}, not closed for {minutes}+ min",
        Detail.DEAD_LETTERS: "{count} dead-letter webhook event(s), failed {attempts} times "
        "and no longer retried (GET /v1/sync/status)",
        Detail.DEAD_LETTERS_NONE: "no dead-letter webhook events left",
        Detail.NO_ATHLETE: "no athlete connected",
        Detail.NEVER_SYNCED: "never synced yet",
        Detail.SYNC_STALE: "no successful sync for {hours:.1f} h (last {last})",
        Detail.SYNC_OK: "syncing again (last {last})",
        Detail.NO_BACKUP: "no backup in {directory}",
        Detail.BACKUP_STALE: "newest backup is {hours:.1f} h old ({name})",
        Detail.BACKUP_OK: "a fresh backup exists ({name})",
    },
    "tr": {
        Detail.CIRCUIT_UNKNOWN: "devre kesici durumu bildirilmedi",
        Detail.CIRCUIT_CLOSED: "Strava devre kesicisi yeniden kapandı",
        Detail.CIRCUIT_OPEN: "Strava devre kesicisi {state}, {minutes}+ dk kapanmadı",
        Detail.DEAD_LETTERS: "{count} dead-letter webhook olayı {attempts} kez başarısız oldu "
        "ve artık denenmiyor (GET /v1/sync/status)",
        Detail.DEAD_LETTERS_NONE: "dead-letter webhook olayı kalmadı",
        Detail.NO_ATHLETE: "bağlı sporcu yok",
        Detail.NEVER_SYNCED: "henüz hiç senkronize edilmedi",
        Detail.SYNC_STALE: "{hours:.1f} sa boyunca başarılı senkronizasyon yok (son {last})",
        Detail.SYNC_OK: "senkronizasyon yeniden çalışıyor (son {last})",
        Detail.NO_BACKUP: "{directory} içinde yedek yok",
        Detail.BACKUP_STALE: "en yeni yedek {hours:.1f} sa önce alınmış ({name})",
        Detail.BACKUP_OK: "yeni bir yedek var ({name})",
    },
}
HEADLINES: Mapping[BotLang, Mapping[Action, str]] = {
    "en": {
        Action.FIRE: "trainsync alert: {detail}",
        Action.RESOLVE: "trainsync resolved: {detail}",
    },
    "tr": {
        Action.FIRE: "trainsync uyarısı: {detail}",
        Action.RESOLVE: "trainsync düzeldi: {detail}",
    },
}
AFTER: Mapping[BotLang, str] = {"en": " (after {minutes} min)", "tr": " ({minutes} dk sonra)"}


def _hours(delta: timedelta) -> float:
    return delta.total_seconds() / 3600


def observe(facts: Facts, now: datetime, limits: Thresholds) -> dict[Condition, Observation]:
    """What each condition looks like now (pure)."""
    minutes = int(limits.circuit_open.total_seconds() // 60)
    if facts.circuit is None:
        circuit = Observation(None, Detail.CIRCUIT_UNKNOWN)
    elif facts.circuit is BreakerState.CLOSED:
        circuit = Observation(False, Detail.CIRCUIT_CLOSED)
    else:
        circuit = Observation(
            True,
            Detail.CIRCUIT_OPEN,
            {"state": facts.circuit.value, "minutes": minutes},
            limits.circuit_open,
        )
    found = {
        Condition.CIRCUIT_OPEN: circuit,
        Condition.DEAD_LETTERS: Observation(
            facts.dead_letters > 0,
            Detail.DEAD_LETTERS,
            {"count": facts.dead_letters, "attempts": MAX_ATTEMPTS},
        )
        if facts.dead_letters
        else Observation(False, Detail.DEAD_LETTERS_NONE),
    }
    if not facts.athletes_active:
        found[Condition.SYNC_STALE] = Observation(False, Detail.NO_ATHLETE)
    elif facts.last_synced_at is None:
        found[Condition.SYNC_STALE] = Observation(None, Detail.NEVER_SYNCED)
    else:
        age = now - facts.last_synced_at
        last = facts.last_synced_at.isoformat()
        found[Condition.SYNC_STALE] = (
            Observation(True, Detail.SYNC_STALE, {"hours": _hours(age), "last": last})
            if age > limits.sync_stale
            else Observation(False, Detail.SYNC_OK, {"last": last})
        )
    if facts.backup_dir is not None:
        backup = facts.newest_backup
        if backup is None:
            found[Condition.BACKUP_STALE] = Observation(
                True, Detail.NO_BACKUP, {"directory": str(facts.backup_dir)}
            )
        else:
            age = now - backup.taken_at
            found[Condition.BACKUP_STALE] = (
                Observation(True, Detail.BACKUP_STALE, {"hours": _hours(age), "name": backup.name})
                if age > limits.backup_max_age
                else Observation(False, Detail.BACKUP_OK, {"name": backup.name})
            )
    return found


def newest_backup(directory: Path) -> Backup | None:
    """The newest complete `trainsync-*.dump.age` (names carry the UTC time; partials start
    with a dot and do not parse). An unreadable directory counts as no backup."""
    try:
        names = [p.name for p in directory.iterdir()]
    except OSError:
        return None
    backups = [b for b in map(parse_name, names) if b is not None]
    return max(backups, key=lambda b: (b.taken_at, b.name), default=None)


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
            reads = ReadRepository(session)
            athletes = await reads.active_athlete_ids()
            last = await reads.last_synced_at(athletes)
        reports = await read_breakers(self._redis)
        backup = None
        if self._backup_dir is not None:
            backup = await asyncio.to_thread(newest_backup, self._backup_dir)
        return Facts(
            circuit=overall_state(reports, now) if reports else None,
            dead_letters=dead,
            athletes_active=bool(athletes),
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
        language=lambda chat: stored_lang(sessionmaker, chat),
    )


def message(
    action: Action, observation: Observation, old: AlertState, now: datetime, lang: BotLang = "en"
) -> str:
    detail = DETAILS[lang][observation.detail].format(**observation.fields)
    text = HEADLINES[lang][action].format(detail=detail)
    if action is Action.RESOLVE and old.bad_since is not None:
        minutes = max(0, int((now - old.bad_since).total_seconds() // 60))
        text += AFTER[lang].format(minutes=minutes)
    return text


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
