"""P5.6: new-activity notifications: one message per live `create`, none for history.

fake_strava delivers webhooks into the in-process API; `drain` plays the worker for webhook
events (with the real enqueue into Redis), `run_like_arq` plays it for notification jobs.
Telegram is respx.
"""

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from functools import partial
from typing import Any

import httpx
import pytest
import respx
from arq.connections import ArqRedis
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.app import create_app as create_fake_strava
from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.support import fake_webhooks
from tests.support.factories import create_athlete, strava_activity
from tests.support.fake_webhooks import activity_event
from tests.support.messages import NEUTRAL_EN
from tests.support.notify import (
    CHAT_ID,
    notification_rows,
    queued_notify_jobs,
    run_like_arq,
    telegram_notify_deps,
)
from tests.support.strava import fake_backed_client
from tests.support.telegram import BOT_URL, error, ok, sent_messages
from trainsync.core.clock import utc_now
from trainsync.core.settings import Settings
from trainsync.db.models import Activity, Athlete, WebhookEvent
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.main import create_app
from trainsync.notify.base import NullNotifier
from trainsync.notify.jobs import NOTIFY_MAX_TRIES, NotifyDeps, send_new_activity
from trainsync.strava.budget import UnlimitedBudget
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import SyncDeps
from trainsync.sync.queue import enqueue_new_activity_notification
from trainsync.sync.webhooks import WebhookDeps, process_event

TARGET = "http://api/webhooks/strava"
SUBSCRIPTION = 999


@pytest.fixture
async def api_app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


@pytest.fixture
def fake_strava_config() -> FakeStravaConfig:
    return FakeStravaConfig(
        seed_activities=1000,
        webhook_subscription_id=SUBSCRIPTION,
        rate_limit_15min=100_000,
        rate_limit_daily=1_000_000,
    )


@pytest.fixture
def fake_strava_app(
    api_app: FastAPI, fake_strava_config: FakeStravaConfig, fake_clock: FakeClock
) -> FastAPI:
    return create_fake_strava(fake_strava_config, fake_clock, httpx.ASGITransport(app=api_app))


@pytest.fixture
def pool(api_app: FastAPI) -> ArqRedis:
    arq_pool: ArqRedis = api_app.state.job_queue.pool
    return arq_pool


@pytest.fixture
async def telegram_http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def telegram() -> AsyncIterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def send(telegram: respx.MockRouter) -> respx.Route:
    return telegram.post(f"{BOT_URL}/sendMessage", name="send").mock(return_value=ok({}))


@pytest.fixture
async def webhook_deps(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
    pool: ArqRedis,
) -> WebhookDeps:
    await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    return WebhookDeps(
        sessionmaker,
        strava,
        utc_now,
        on_new_activity=partial(enqueue_new_activity_notification, pool),
    )


async def drain(deps: WebhookDeps) -> list[str]:
    async with deps.sessionmaker() as session:
        ids = (
            await session.scalars(
                select(WebhookEvent.id)
                .where(WebhookEvent.status == "pending")
                .order_by(WebhookEvent.id)
            )
        ).all()
    return [(await process_event(deps, event_id)).status for event_id in ids]


def create_event(fake: FakeStravaState, activity_id: int, offset: int = 0) -> Any:
    return activity_event(
        activity_id,
        "create",
        owner_id=fake.default_athlete_id,
        subscription_id=SUBSCRIPTION,
        event_time=1_760_000_000 + offset,
    )


async def test_duplicate_webhook_delivery_sends_one_notification(
    webhook_deps: WebhookDeps,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    pool: ArqRedis,
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_http: httpx.AsyncClient,
    send: respx.Route,
) -> None:
    new = fake_strava.apply_change(
        "create", athlete_id=None, activity_id=None, fields={"name": "Lunch Run"}
    )
    assert new is not None
    # The same event delivered 4 times, then a second `create` for the same activity with a
    # different event_time (a distinct event as far as the dedup key goes).
    event = create_event(fake_strava, new.id)
    await fake_webhooks.fire(fake_strava_client, TARGET, [event], mode="duplicate", duplicates=4)
    await fake_webhooks.fire(fake_strava_client, TARGET, [create_event(fake_strava, new.id, 5)])
    assert await drain(webhook_deps) == ["upserted", "upserted"]

    # Both create events enqueue, but the job id makes it one job.
    assert await queued_notify_jobs(pool) == [(f"notify:{new.id}", new.id)]

    deps = telegram_notify_deps(sessionmaker, telegram_http)
    assert await send_new_activity(deps, new.id) == "sent"
    # Even if the job ran again (re-enqueued after arq dropped its result), no second message.
    assert await send_new_activity(deps, new.id) == "duplicate"

    [message] = sent_messages(send)
    assert message["chat_id"] == CHAT_ID
    assert message["text"].splitlines()[:2] == ["New activity", "🏃 Lunch Run"]
    assert message["text"].endswith(f"https://dash.test/activities/{new.id}")
    assert await notification_rows(sessionmaker) == 1


async def test_backfill_of_1000_activities_sends_no_notification(
    webhook_deps: WebhookDeps,
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    pool: ArqRedis,
    sessionmaker: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    fake_strava_token: dict[str, Any],
    send: respx.Route,
) -> None:
    async with sessionmaker() as session:
        athlete_id = (await session.scalars(select(Athlete.id))).one()
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    outcome = await run_backfill(
        SyncDeps(sessionmaker, strava, UnlimitedBudget(), utc_now), athlete_id
    )
    assert outcome.status == "succeeded"
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Activity)) == 1000

    # Edits of history through webhooks are not news either.
    some_id = next(iter(fake_strava.activities))
    update = activity_event(
        some_id,
        "update",
        owner_id=fake_strava.default_athlete_id,
        subscription_id=SUBSCRIPTION,
        event_time=1_760_000_100,
        updates={"title": "Renamed"},
    )
    await fake_webhooks.fire(fake_strava_client, TARGET, [update])
    assert await drain(webhook_deps) == ["upserted"]

    assert await queued_notify_jobs(pool) == []
    assert await notification_rows(sessionmaker) == 0
    assert send.call_count == 0


async def test_failed_send_releases_the_claim_and_gives_up_after_max_tries(
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_http: httpx.AsyncClient,
    telegram: respx.MockRouter,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(athlete_id, [strava_activity(7)])
    route = telegram.post(f"{BOT_URL}/sendMessage").mock(return_value=error(400, "chat not found"))

    deps = telegram_notify_deps(sessionmaker, telegram_http)
    outcome, retries = await run_like_arq(deps, 7, max_tries=NOTIFY_MAX_TRIES)
    assert outcome == "gave_up"
    assert [r.defer_score for r in retries] == [
        int(timedelta(seconds=s).total_seconds() * 1000) for s in (10, 30, 90, 270)
    ]
    assert route.call_count == NOTIFY_MAX_TRIES  # 4xx: no in-process retry
    assert await notification_rows(sessionmaker) == 0  # released: a later run may still send


async def test_retry_after_from_telegram_sets_the_minimum_deferral(
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_http: httpx.AsyncClient,
    telegram: respx.MockRouter,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(athlete_id, [strava_activity(7)])
    telegram.post(f"{BOT_URL}/sendMessage").mock(
        side_effect=[error(429, "slow", retry_after=120)] * 2 + [ok({})]
    )
    outcome, retries = await run_like_arq(
        telegram_notify_deps(sessionmaker, telegram_http), 7, max_tries=NOTIFY_MAX_TRIES
    )
    assert outcome == "sent"
    assert [r.defer_score for r in retries] == [120_000]


async def test_unknown_delivery_keeps_the_claim(
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_http: httpx.AsyncClient,
    telegram: respx.MockRouter,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(athlete_id, [strava_activity(7)])
    route = telegram.post(f"{BOT_URL}/sendMessage").mock(side_effect=httpx.ReadTimeout("slow"))
    deps = telegram_notify_deps(sessionmaker, telegram_http)
    assert await send_new_activity(deps, 7) == "unknown"
    assert await send_new_activity(deps, 7) == "duplicate"
    assert route.call_count == 1  # never risk a second message
    assert await notification_rows(sessionmaker) == 1


async def test_deleted_activity_and_disabled_notifier_send_nothing(
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_http: httpx.AsyncClient,
    send: respx.Route,
) -> None:
    athlete_id = await create_athlete(sessionmaker)
    async with sessionmaker.begin() as session:
        repo = ActivityRepository(session)
        await repo.upsert_many(athlete_id, [strava_activity(7), strava_activity(8)])
        await repo.soft_delete(8)
    deps = telegram_notify_deps(sessionmaker, telegram_http)
    assert await send_new_activity(deps, 8) == "skipped"
    assert await send_new_activity(deps, 999) == "skipped"
    disabled = NotifyDeps(sessionmaker, NullNotifier(), None, "", utc_now, NEUTRAL_EN)
    assert await send_new_activity(disabled, 7) == "disabled"
    assert await send_new_activity(replace(deps, notifier=NullNotifier()), 7) == "sent"
    assert send.call_count == 0
