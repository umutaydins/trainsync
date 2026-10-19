"""P7.8 stack alerts against real Postgres and Redis: the facts the worker reads, and the alert
state surviving a "restart" (a fresh store over the same Redis)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.support.factories import create_athlete
from trainsync.integrations.notifier import NullNotifier
from trainsync.integrations.strava.breaker import BreakerState
from trainsync.integrations.strava.breaker_status import RedisBreakerPublisher
from trainsync.modules.notifications.alerts import (
    AlertDeps,
    AlertState,
    Condition,
    RedisAlertStore,
    StackFacts,
    build_alert_deps,
    run_alerts,
)
from trainsync.modules.sync.models import SyncKind, SyncRun, SyncStatus, WebhookEvent, WebhookStatus
from trainsync.modules.sync.webhook_repository import MAX_ATTEMPTS

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


class Recorder:
    channel = "test"

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def send(self, chat_ref: str, text: str) -> None:
        self.texts.append(text)


async def test_facts_from_the_database_redis_and_the_backup_folder(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, tmp_path: Path
) -> None:
    facts = await StackFacts(sessionmaker, redis, None).collect(NOW)
    assert facts.circuit is None
    assert facts.dead_letters == 0
    assert not facts.athletes_active
    assert facts.backup_dir is None

    athlete = await create_athlete(sessionmaker)
    async with sessionmaker.begin() as session:
        session.add(
            SyncRun(
                athlete_id=athlete,
                kind=SyncKind.INCREMENTAL,
                status=SyncStatus.SUCCEEDED,
                finished_at=NOW - timedelta(hours=3),
            )
        )
        session.add(
            WebhookEvent(
                dedup_key="dead-1",
                payload={},
                status=WebhookStatus.FAILED,
                attempts=MAX_ATTEMPTS,
            )
        )
        session.add(WebhookEvent(dedup_key="retrying", payload={}, status=WebhookStatus.FAILED))
    await RedisBreakerPublisher(redis, "worker@test:1", lambda: NOW)(
        BreakerState.OPEN, NOW + timedelta(seconds=30)
    )
    (tmp_path / "trainsync-20261017-033000.dump.age").write_text("x")

    facts = await StackFacts(sessionmaker, redis, tmp_path).collect(NOW)
    assert facts.circuit is BreakerState.OPEN
    assert facts.dead_letters == 1
    assert facts.athletes_active
    assert facts.last_synced_at == NOW - timedelta(hours=3)
    assert facts.backup_dir == str(tmp_path)
    assert facts.newest_backup is not None
    assert facts.newest_backup.taken_at == datetime(2026, 10, 17, 3, 30, tzinfo=UTC)


async def test_alert_state_survives_a_worker_restart(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    async with sessionmaker.begin() as session:
        session.add(
            WebhookEvent(
                dedup_key="dead-1", payload={}, status=WebhookStatus.FAILED, attempts=MAX_ATTEMPTS
            )
        )
    notifier = Recorder()

    def deps(now: datetime) -> AlertDeps:
        # A new store and facts source each time: nothing is carried in memory.
        return AlertDeps(
            StackFacts(sessionmaker, redis, None),
            RedisAlertStore(redis),
            notifier,
            "42",
            lambda: now,
        )

    await run_alerts(deps(NOW))
    await run_alerts(deps(NOW + timedelta(minutes=5)))
    assert len(notifier.texts) == 1
    assert "1 dead-letter webhook event(s)" in notifier.texts[0]
    stored = await RedisAlertStore(redis).load(Condition.DEAD_LETTERS)
    assert stored == AlertState(NOW, alerted=True)
    assert await redis.ttl("alert:dead_letters") == -1  # no expiry

    async with sessionmaker.begin() as session:
        await session.execute(WebhookEvent.__table__.delete())
    await run_alerts(deps(NOW + timedelta(minutes=10)))
    assert notifier.texts[-1] == (
        "trainsync resolved: no dead-letter webhook events left (after 10 min)"
    )


async def test_build_alert_deps_reads_the_backup_dir(redis: Redis, tmp_path: Path) -> None:
    settings = make_settings(backup_dir=str(tmp_path), telegram_bot_token="")
    built = build_alert_deps(
        settings, async_sessionmaker(), redis, NullNotifier(), None, lambda: NOW
    )
    assert built.chat_ref is None
    assert isinstance(built.facts, StackFacts)
    assert isinstance(built.store, RedisAlertStore)
