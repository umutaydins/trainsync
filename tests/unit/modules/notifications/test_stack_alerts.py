"""Stack-internal alerts (P7.8): for every condition, starting sends one alert, persisting sends
nothing, clearing sends one recovery. Injected clock, in-memory state and a recording notifier."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.conftest import make_settings
from trainsync.core.settings import BotLang, Settings
from trainsync.integrations.notifier import DeliveryUnknownError, NotifyFailedError
from trainsync.integrations.strava.breaker import BreakerState
from trainsync.modules.notifications.alerts import (
    DETAILS,
    Action,
    AlertDeps,
    AlertState,
    Condition,
    Detail,
    Facts,
    Observation,
    Thresholds,
    alerts_tick,
    newest_backup,
    observe,
    run_alerts,
    step,
)
from trainsync.ops.retention import Backup

T0 = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
FRESH_BACKUP = Backup("trainsync-20261018-003000.dump.age", T0 - timedelta(hours=8, minutes=30))
HEALTHY = Facts(
    circuit=BreakerState.CLOSED,
    dead_letters=0,
    athletes_active=True,
    last_synced_at=T0,
    backup_dir="/backups",
    newest_backup=FRESH_BACKUP,
)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


class FakeFacts:
    def __init__(self, clock: Clock) -> None:
        self.facts = HEALTHY
        self.clock = clock

    async def collect(self, now: datetime) -> Facts:
        return self.facts


class MemoryStore:
    def __init__(self) -> None:
        self.states: dict[Condition, AlertState] = {}

    async def load(self, condition: Condition) -> AlertState:
        return self.states.get(condition, AlertState())

    async def save(self, condition: Condition, state: AlertState) -> None:
        self.states[condition] = state


class Recorder:
    channel = "test"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.error: Exception | None = None

    async def send(self, chat_ref: str, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append((chat_ref, text))


class Harness:
    def __init__(self, chat_ref: str | None = "42") -> None:
        self.clock = Clock()
        self.facts = FakeFacts(self.clock)
        self.store = MemoryStore()
        self.notifier = Recorder()
        self.deps = AlertDeps(self.facts, self.store, self.notifier, chat_ref, self.clock)

    async def tick(self, minutes: int = 5, **changes: object) -> list[str]:
        """Advance the clock, apply fact changes, run once; the texts sent by this tick."""
        self.clock.now += timedelta(minutes=minutes)
        if changes:
            self.facts.facts = replace(self.facts.facts, **changes)  # type: ignore[arg-type]
        before = len(self.notifier.sent)
        await run_alerts(self.deps)
        return [text for _, text in self.notifier.sent[before:]]

    def keep_fresh(self) -> dict[str, object]:
        """Facts that stay healthy as the clock moves: a sync and a backup just now."""
        return {
            "last_synced_at": self.clock.now + timedelta(minutes=5),
            "newest_backup": replace(FRESH_BACKUP, taken_at=self.clock.now),
        }


async def test_healthy_stack_sends_nothing() -> None:
    h = Harness()
    for _ in range(3):
        assert await h.tick(**h.keep_fresh()) == []
    assert all(s == AlertState() for s in h.store.states.values())


async def test_circuit_open_alerts_after_30_minutes_once_and_recovers_once() -> None:
    h = Harness()
    sent: list[str] = []
    sent += await h.tick(**h.keep_fresh(), circuit=BreakerState.OPEN)  # starts: grace begins
    for _ in range(5):  # 25 min in total: still inside the grace
        sent += await h.tick(**h.keep_fresh(), circuit=BreakerState.HALF_OPEN)
    assert sent == []
    fired = await h.tick(**h.keep_fresh())  # 30 min
    assert fired == ["trainsync alert: Strava circuit breaker half_open, not closed for 30+ min"]
    for _ in range(4):  # persists
        assert await h.tick(**h.keep_fresh()) == []
    resolved = await h.tick(**h.keep_fresh(), circuit=BreakerState.CLOSED)
    assert resolved == ["trainsync resolved: Strava circuit breaker is closed again (after 55 min)"]
    assert await h.tick(**h.keep_fresh()) == []


async def test_a_short_open_circuit_never_alerts() -> None:
    h = Harness()
    assert await h.tick(**h.keep_fresh(), circuit=BreakerState.OPEN) == []
    assert await h.tick(**h.keep_fresh(), circuit=BreakerState.CLOSED) == []
    assert await h.tick(**h.keep_fresh(), circuit=BreakerState.OPEN) == []
    assert h.store.states[Condition.CIRCUIT_OPEN].bad_since == h.clock.now


async def test_unknown_circuit_keeps_the_grace_running() -> None:
    """The open breaker's Redis key expires between probes: no report is not a recovery."""
    h = Harness()
    await h.tick(**h.keep_fresh(), circuit=BreakerState.OPEN)
    for _ in range(5):
        assert await h.tick(**h.keep_fresh(), circuit=None) == []
    assert await h.tick(**h.keep_fresh(), circuit=BreakerState.OPEN) != []


async def test_dead_letters_alert_once_and_recover_once() -> None:
    h = Harness()
    fired = await h.tick(**h.keep_fresh(), dead_letters=2)
    assert fired == [
        "trainsync alert: 2 dead-letter webhook event(s), failed 8 times and no longer retried "
        "(GET /v1/sync/status)"
    ]
    assert await h.tick(**h.keep_fresh(), dead_letters=3) == []
    assert await h.tick(**h.keep_fresh()) == []
    resolved = await h.tick(**h.keep_fresh(), dead_letters=0)
    assert resolved == ["trainsync resolved: no dead-letter webhook events left (after 15 min)"]


async def test_backup_older_than_36_hours_alerts_once_and_recovers_once() -> None:
    h = Harness()
    old = replace(FRESH_BACKUP, taken_at=T0 - timedelta(hours=36))
    sync = {"last_synced_at": T0 + timedelta(days=1)}
    fired = await h.tick(**sync, newest_backup=old)  # 36 h 5 min old
    assert fired == [f"trainsync alert: newest backup is 36.1 h old ({old.name})"]
    assert await h.tick(**sync) == []
    assert await h.tick(**sync, newest_backup=None) == []  # folder emptied: still the same alert
    new = Backup("trainsync-20261018-091500.dump.age", T0 + timedelta(minutes=15))
    resolved = await h.tick(**sync, newest_backup=new)
    assert resolved == [f"trainsync resolved: a fresh backup exists ({new.name}) (after 15 min)"]


async def test_missing_backup_alerts_and_unchecked_backups_never_do() -> None:
    h = Harness()
    assert await h.tick(last_synced_at=T0, newest_backup=None) == [
        "trainsync alert: no backup in /backups"
    ]
    unchecked = Harness()
    assert await unchecked.tick(last_synced_at=T0, backup_dir=None, newest_backup=None) == []
    assert Condition.BACKUP_STALE not in unchecked.store.states


async def test_sync_stale_after_2_hours_alerts_once_and_recovers_once() -> None:
    h = Harness()
    fresh_backup = {"newest_backup": replace(FRESH_BACKUP, taken_at=T0)}
    assert await h.tick(minutes=115, **fresh_backup) == []  # 1 h 55 min since T0
    fired = await h.tick(minutes=10)
    assert fired == [
        "trainsync alert: no successful sync for 2.1 h (last 2026-10-18T09:00:00+00:00)"
    ]
    assert await h.tick() == []
    synced = h.clock.now + timedelta(minutes=5)
    resolved = await h.tick(last_synced_at=synced)
    assert resolved == [
        f"trainsync resolved: syncing again (last {synced.isoformat()}) (after 10 min)"
    ]


async def test_sync_is_not_stale_without_athletes_or_before_the_first_sync() -> None:
    h = Harness()
    backup = {"newest_backup": replace(FRESH_BACKUP, taken_at=T0 + timedelta(hours=5))}
    assert await h.tick(minutes=300, athletes_active=False, **backup) == []
    assert await h.tick(athletes_active=True, last_synced_at=None) == []
    assert Condition.SYNC_STALE not in h.store.states  # never bad: nothing to remember


async def test_off_without_a_telegram_target() -> None:
    h = Harness(chat_ref=None)
    assert await h.tick(dead_letters=5) == []
    assert h.store.states == {}
    assert await alerts_tick({"trainsync_alerts": h.deps}) == {}


async def test_failed_send_is_retried_next_tick_and_unknown_counts_as_sent() -> None:
    h = Harness()
    h.notifier.error = NotifyFailedError("telegram down")
    assert await h.tick(**h.keep_fresh(), dead_letters=1) == []
    assert h.store.states[Condition.DEAD_LETTERS].alerted is False
    h.notifier.error = None
    assert len(await h.tick(**h.keep_fresh())) == 1  # retried
    h.notifier.error = NotifyFailedError("telegram down")
    assert await h.tick(**h.keep_fresh(), dead_letters=0) == []
    assert h.store.states[Condition.DEAD_LETTERS].alerted is True  # recovery still owed
    h.notifier.error = DeliveryUnknownError("timeout")
    assert await h.tick(**h.keep_fresh()) == []
    h.notifier.error = None
    assert await h.tick(**h.keep_fresh()) == []  # the unknown one is not repeated
    assert h.store.states[Condition.DEAD_LETTERS] == AlertState()


async def test_tick_reports_outcomes_by_name() -> None:
    h = Harness()
    h.clock.now += timedelta(minutes=5)
    h.facts.facts = replace(HEALTHY, dead_letters=1, last_synced_at=h.clock.now)
    outcomes = await alerts_tick({"trainsync_alerts": h.deps})
    assert outcomes["dead_letters"] == "sent_fire"
    assert outcomes["circuit_open"] == "quiet"


@pytest.mark.parametrize(
    ("state", "bad", "expected"),
    [
        (AlertState(), None, (AlertState(), Action.NONE)),
        (AlertState(T0, alerted=True), None, (AlertState(T0, alerted=True), Action.NONE)),
        (AlertState(), False, (AlertState(), Action.NONE)),
        (AlertState(T0, alerted=True), False, (AlertState(), Action.RESOLVE)),
        (AlertState(), True, (AlertState(T0, alerted=True), Action.FIRE)),
        (AlertState(T0, alerted=True), True, (AlertState(T0, alerted=True), Action.NONE)),
    ],
)
def test_step(state: AlertState, bad: bool | None, expected: tuple[AlertState, Action]) -> None:
    assert step(state, bad, T0) == expected


def test_state_json_round_trip_and_garbage() -> None:
    state = AlertState(T0, alerted=True)
    assert AlertState.from_json(state.to_json()) == state
    assert AlertState.from_json(AlertState().to_json().encode()) == AlertState()
    for raw in (None, "", "[]", "{}", '{"bad_since": "nope", "alerted": true}'):
        assert AlertState.from_json(raw) == AlertState()


def test_thresholds_from_settings(settings: Settings) -> None:
    assert Thresholds.from_settings(settings) == Thresholds()
    assert settings.backup_dir == ""
    custom = make_settings(alert_circuit_open_minutes=10, alert_sync_stale_hours=0.5)
    limits = Thresholds.from_settings(custom)
    assert limits.circuit_open == timedelta(minutes=10)
    assert limits.sync_stale == timedelta(minutes=30)


def test_observe_without_breaker_reports_is_unknown() -> None:
    found = observe(replace(HEALTHY, circuit=None), T0, Thresholds())
    assert found[Condition.CIRCUIT_OPEN] == Observation(None, Detail.CIRCUIT_UNKNOWN)


def test_newest_backup_ignores_partials_and_strangers(tmp_path: Path) -> None:
    assert newest_backup(tmp_path / "missing") is None
    assert newest_backup(tmp_path) is None
    for name in (
        "trainsync-20261016-033000.dump.age",
        "trainsync-20261017-120000-predeploy1a2b3c4.dump.age",
        "trainsync-20261017-033000.counts.json",
        ".trainsync-20261018-033000.dump.age.partial",
        "notes.txt",
    ):
        (tmp_path / name).write_text("x")
    newest = newest_backup(tmp_path)
    assert newest is not None
    assert newest.name == "trainsync-20261017-120000-predeploy1a2b3c4.dump.age"


async def test_alerts_follow_the_chat_language() -> None:
    """P6.12: the language stored for the chat (`/lang`) is read at send time (ADR 0031)."""
    h = Harness()
    asked: list[str] = []

    async def language(chat: str) -> BotLang | None:
        asked.append(chat)
        return "tr"

    h.deps = replace(h.deps, language=language)
    await h.tick(**h.keep_fresh(), circuit=BreakerState.OPEN)
    fired = await h.tick(minutes=30, **h.keep_fresh())
    assert fired == ["trainsync uyarısı: Strava devre kesicisi open, 30+ dk kapanmadı"]
    resolved = await h.tick(**h.keep_fresh(), circuit=BreakerState.CLOSED)
    assert resolved == ["trainsync düzeldi: Strava devre kesicisi yeniden kapandı (35 dk sonra)"]
    assert asked == ["42", "42"]


def test_every_alert_detail_exists_in_both_languages() -> None:
    for lang in ("en", "tr"):
        assert set(DETAILS[lang]) == set(Detail)
