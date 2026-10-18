"""P3.3: webhook events end in the correct final state regardless of duplicates or ordering.

fake_strava delivers its webhooks straight into the in-process trainsync app (ASGI transport);
`drain` then plays the worker, processing pending events in arrival order.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from arq import Retry
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.app import create_app as create_fake_strava
from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.support import fake_webhooks
from tests.support.factories import create_athlete, strava_activity
from tests.support.fake_webhooks import activity_event
from tests.support.strava import fake_backed_client
from trainsync.core.clock import utc_now
from trainsync.core.crypto import TokenCipher
from trainsync.core.settings import Settings
from trainsync.db.models import Activity, Athlete, OAuthToken, WebhookEvent
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.tokens import SqlTokenStore, Tokens
from trainsync.main import create_app
from trainsync.strava.budget import RateBudget
from trainsync.strava.errors import CircuitOpen, StravaAuthError
from trainsync.strava.models import StravaActivity
from trainsync.strava.ratelimit import parse_rate_limit
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import CTX_KEY, SyncDeps
from trainsync.sync.webhooks import WebhookDeps, process_event, process_webhook_event

TARGET = "http://api/webhooks/strava"
SUBSCRIPTION = 999  # matches the test settings
GET_ACTIVITY = "GET /api/v3/activities/{activity_id}"


@pytest.fixture
async def api_app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
def fake_strava_app(api_app: FastAPI, fake_clock: FakeClock) -> FastAPI:
    config = FakeStravaConfig(
        seed_activities=5,
        webhook_subscription_id=SUBSCRIPTION,
        rate_limit_15min=10_000,
        rate_limit_daily=100_000,
    )
    return create_fake_strava(config, fake_clock, httpx.ASGITransport(app=api_app))


@dataclass
class World:
    deps: WebhookDeps
    athlete_id: int
    fake: FakeStravaState
    fake_client: httpx.AsyncClient
    sessionmaker: async_sessionmaker[AsyncSession]

    async def drain(self) -> list[str]:
        async with self.sessionmaker() as session:
            ids = (
                await session.scalars(
                    select(WebhookEvent.id)
                    .where(WebhookEvent.status == "pending")
                    .order_by(WebhookEvent.id)
                )
            ).all()
        return [(await process_event(self.deps, event_id)).status for event_id in ids]

    def fetches(self) -> int:
        return sum(self.fake.stats_json()["requests"].get(GET_ACTIVITY, {}).values())

    async def row(self, strava_activity_id: int) -> Activity | None:
        async with self.sessionmaker() as session:
            return await session.scalar(
                select(Activity).where(Activity.strava_activity_id == strava_activity_id)
            )

    def event(self, activity_id: int, aspect: Any, offset: int = 0, **updates: Any) -> Any:
        return activity_event(
            activity_id,
            aspect,
            owner_id=self.fake.default_athlete_id,
            subscription_id=SUBSCRIPTION,
            event_time=1_760_000_000 + offset,
            updates=updates,
        )


@pytest.fixture
async def world(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> World:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    return World(
        WebhookDeps(sessionmaker, strava, utc_now),
        athlete_id,
        fake_strava,
        fake_strava_client,
        sessionmaker,
    )


async def _statuses(sessionmaker: async_sessionmaker[AsyncSession]) -> list[str]:
    async with sessionmaker() as session:
        return list((await session.scalars(select(WebhookEvent.status))).all())


async def test_out_of_order_lifecycle_of_a_new_activity_leaves_nothing_visible(
    world: World,
) -> None:
    scenario = await fake_webhooks.activity_lifecycle(world.fake_client, TARGET, out_of_order=True)
    assert scenario.report.delivered == 3
    assert scenario.activity_id is not None
    await world.drain()
    # Never seen alive by us (Strava already deleted it when we fetched): nothing to show.
    row = await world.row(scenario.activity_id)
    assert row is None or row.deleted_at is not None
    assert set(await _statuses(world.sessionmaker)) == {"processed"}


async def test_out_of_order_update_and_delete_of_a_synced_activity_soft_deletes(
    world: World,
) -> None:
    created = await fake_webhooks.activity_lifecycle(world.fake_client, TARGET, delete=False)
    activity_id = created.activity_id
    assert activity_id is not None
    await world.drain()
    assert (row := await world.row(activity_id)) is not None
    assert row.deleted_at is None

    # The athlete renames, then deletes; Strava delivers delete first.
    response = await world.fake_client.post(
        "/_control/activities", json={"action": "delete", "id": activity_id}
    )
    response.raise_for_status()
    events = [
        world.event(activity_id, "update", 10, title="x"),
        world.event(activity_id, "delete", 11),
    ]
    report = await fake_webhooks.fire(world.fake_client, TARGET, events, mode="out_of_order")
    assert [d.event.aspect_type for d in report.deliveries] == ["delete", "update"]
    await world.drain()

    row = await world.row(activity_id)
    assert row is not None
    assert row.deleted_at is not None


async def test_create_and_update_in_reverse_order_end_with_latest_title(world: World) -> None:
    scenario = await fake_webhooks.activity_lifecycle(
        world.fake_client, TARGET, delete=False, out_of_order=True, title="Tempo 3x10'"
    )
    assert [d.event.aspect_type for d in scenario.report.deliveries] == ["update", "create"]
    assert scenario.activity_id is not None
    assert await world.drain() == ["upserted", "upserted"]
    row = await world.row(scenario.activity_id)
    assert row is not None
    assert (row.name, row.deleted_at) == ("Tempo 3x10'", None)


async def test_duplicate_deliveries_are_processed_once(world: World) -> None:
    activity_id = next(iter(world.fake.activities))
    event = world.event(activity_id, "update", title="dup")
    report = await fake_webhooks.fire(
        world.fake_client, TARGET, [event], mode="duplicate", duplicates=5
    )
    assert report.delivered == 5
    before = world.fetches()
    assert await world.drain() == ["upserted"]
    assert world.fetches() - before == 1
    assert await _statuses(world.sessionmaker) == ["processed"]
    assert await world.drain() == []


async def test_deauthorization_removes_tokens_and_data(
    world: World, integration_settings: Settings
) -> None:
    store = SqlTokenStore(world.sessionmaker, TokenCipher.from_settings(integration_settings))
    await store.save(
        world.athlete_id, Tokens("a", "r", datetime.now(UTC) + timedelta(hours=1), "read")
    )
    async with world.sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(
            world.athlete_id, [strava_activity(i) for i in range(1, 11)]
        )

    report = await fake_webhooks.deauthorize(world.fake_client, TARGET)
    assert report.report.delivered == 1
    assert await world.drain() == ["deauthorized"]

    async with world.sessionmaker() as session:
        athlete = await session.get(Athlete, world.athlete_id)
        assert athlete is not None
        assert athlete.active is False
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 0
        assert await session.scalar(select(func.count()).select_from(Activity)) == 0

    # Later events for this athlete are processed without fetching anything.
    activity_id = next(iter(world.fake.activities))
    before = world.fetches()
    await fake_webhooks.fire(world.fake_client, TARGET, [world.event(activity_id, "create", 20)])
    assert await world.drain() == ["ignored"]
    assert world.fetches() == before
    assert await world.row(activity_id) is None


async def test_unknown_owner_is_processed_and_ignored(world: World) -> None:
    event = world.event(1, "create").model_copy(update={"owner_id": 424242})
    await fake_webhooks.fire(world.fake_client, TARGET, [event])
    assert await world.drain() == ["ignored"]
    assert await _statuses(world.sessionmaker) == ["processed"]


async def test_webhook_fetch_runs_while_backfill_is_paused_by_budget(
    world: World,
    redis: Redis,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    budget = RateBudget(redis)
    await budget.record(
        parse_rate_limit({"X-RateLimit-Limit": "100,1000", "X-RateLimit-Usage": "85,100"})
        or pytest.fail("bad headers")
    )
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"], budget=budget
    )
    paused = await run_backfill(
        SyncDeps(world.sessionmaker, strava, budget, utc_now), world.athlete_id
    )
    assert paused.status == "paused"

    activity_id = next(iter(world.fake.activities))
    await fake_webhooks.fire(world.fake_client, TARGET, [world.event(activity_id, "update")])
    deps = WebhookDeps(world.sessionmaker, strava, utc_now)
    async with world.sessionmaker() as session:
        event_id = await session.scalar(select(WebhookEvent.id))
    assert event_id is not None
    assert (await process_event(deps, event_id)).status == "upserted"
    assert await world.row(activity_id) is not None


@dataclass
class Raising:
    error: Exception

    async def get_activity(self, athlete_id: int, activity_id: int, **_: Any) -> StravaActivity:
        raise self.error


async def _one_event(world: World) -> int:
    activity_id = next(iter(world.fake.activities))
    await fake_webhooks.fire(world.fake_client, TARGET, [world.event(activity_id, "update")])
    async with world.sessionmaker() as session:
        event_id = await session.scalar(select(WebhookEvent.id))
    assert event_id is not None
    return event_id


async def test_open_circuit_puts_event_back_to_pending_and_defers_the_job(world: World) -> None:
    event_id = await _one_event(world)
    retry_at = datetime.now(UTC) + timedelta(seconds=30)
    deps = WebhookDeps(world.sessionmaker, Raising(CircuitOpen(retry_at)), utc_now)
    context = SimpleContext(deps)
    with pytest.raises(Retry) as exc_info:
        await process_webhook_event({CTX_KEY: context}, event_id)
    assert exc_info.value.defer_score is not None
    assert 29 <= exc_info.value.defer_score / 1000 <= 33
    async with world.sessionmaker() as session:
        event = await session.get(WebhookEvent, event_id)
        assert event is not None
        assert (event.status, event.attempts) == ("pending", 1)


async def test_other_errors_mark_the_event_failed(world: World) -> None:
    event_id = await _one_event(world)
    deps = WebhookDeps(world.sessionmaker, Raising(StravaAuthError("revoked")), utc_now)
    assert (await process_event(deps, event_id)).status == "failed"
    assert await _statuses(world.sessionmaker) == ["failed"]
    # A processed event cannot be claimed again.
    assert (await process_event(world.deps, event_id)).status == "upserted"
    assert (await process_event(world.deps, event_id)).status == "skipped"


@dataclass
class SimpleContext:
    """The parts of WorkerContext the webhook job uses."""

    deps: WebhookDeps

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self.deps.sessionmaker

    @property
    def strava(self) -> Any:
        return self.deps.strava

    def clock(self) -> datetime:
        return self.deps.clock()

    @property
    def redis(self) -> Any:
        return None  # only used to enqueue notifications after a `create`, not reached here
