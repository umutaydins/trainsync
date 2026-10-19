"""Stack alert conditions (ADR 0027), pure: the facts of one tick, what each condition looks like,
and the per-condition state machine (fire once when it starts, resolve once when it clears)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from trainsync.core.settings import Settings
from trainsync.integrations.strava.breaker import BreakerState
from trainsync.modules.sync.webhook_repository import MAX_ATTEMPTS
from trainsync.ops.retention import Backup, parse_name

SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60


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


def _hours(delta: timedelta) -> float:
    return delta.total_seconds() / SECONDS_PER_HOUR


def observe(facts: Facts, now: datetime, limits: Thresholds) -> dict[Condition, Observation]:
    """What each condition looks like now (pure)."""
    minutes = int(limits.circuit_open.total_seconds() // SECONDS_PER_MINUTE)
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
