"""Failure mode: Telegram down when a new activity arrives → the notification job is retried
with backoff and the message goes out exactly once when Telegram is back.

The whole path runs: fake_strava delivers the `create` webhook into the API, the webhook event is
processed (fetch + upsert + enqueue `notify:{id}` into Redis), then the notification job runs the
way arq runs it, against a Telegram that fails (5xx, refused connections) for two tries.
"""

from functools import partial
from typing import Any

import httpx
import respx
from arq.connections import ArqRedis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.fault.conftest import API_URL, SUBSCRIPTION
from tests.fault.helpers import drain_webhooks, metric
from tests.support import fake_webhooks
from tests.support.factories import create_athlete
from tests.support.fake_webhooks import activity_event
from tests.support.notify import (
    CHAT_ID,
    notification_rows,
    queued_notify_jobs,
    run_like_arq,
    telegram_notify_deps,
)
from tests.support.strava import fake_backed_client
from tests.support.telegram import BOT_URL, SleepRecorder, ok, sent_messages
from trainsync.core.clock import utc_now
from trainsync.core.settings import Settings
from trainsync.notify.jobs import NOTIFY_MAX_TRIES
from trainsync.sync.queue import enqueue_new_activity_notification
from trainsync.sync.webhooks import WebhookDeps

TARGET = f"{API_URL}/webhooks/strava"


@respx.mock
async def test_telegram_down_then_back_sends_exactly_one_message(
    api_app: FastAPI,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    new = fake_strava.apply_change(
        "create", athlete_id=None, activity_id=None, fields={"name": "Tempo Run"}
    )
    assert new is not None
    event = activity_event(
        new.id,
        "create",
        owner_id=fake_strava.default_athlete_id,
        subscription_id=SUBSCRIPTION,
        event_time=1_760_000_000,
    )
    report = await fake_webhooks.fire(fake_strava_client, TARGET, [event])
    assert report.delivered == 1

    pool: ArqRedis = api_app.state.job_queue.pool
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    webhook_deps = WebhookDeps(
        sessionmaker,
        strava,
        utc_now,
        on_new_activity=partial(enqueue_new_activity_notification, pool),
    )
    assert await drain_webhooks(webhook_deps, sessionmaker) == ["upserted"]
    assert await queued_notify_jobs(pool) == [(f"notify:{new.id}", new.id)]

    send = respx.post(f"{BOT_URL}/sendMessage").mock(
        side_effect=[
            httpx.Response(503),  # try 1, attempt 1
            httpx.ConnectError("connection refused"),  # try 1, attempt 2
            httpx.Response(502),  # try 2, attempt 1
            httpx.Response(500),  # try 2, attempt 2
            httpx.ConnectError("connection refused"),  # try 3, attempt 1
            ok({}),  # try 3, attempt 2: Telegram is back
        ]
    )
    sleep = SleepRecorder()
    telegram_http = httpx.AsyncClient()
    deps = telegram_notify_deps(sessionmaker, telegram_http, sleep)
    failed_before = metric("notifications_total", channel="telegram", outcome="failed")

    outcome, retries = await run_like_arq(deps, new.id, max_tries=NOTIFY_MAX_TRIES)

    assert outcome == "sent"
    assert [r.defer_score for r in retries] == [10_000, 30_000]  # arq backoff between tries
    assert sleep.sleeps == [1.0, 1.0, 1.0]  # one short in-process retry per try
    assert send.call_count == 6
    [message] = sent_messages(send)
    assert message["chat_id"] == CHAT_ID
    assert "Tempo Run" in message["text"]
    assert metric("notifications_total", channel="telegram", outcome="failed") - failed_before == 2
    assert await notification_rows(sessionmaker) == 1

    # The job running once more (a duplicate enqueue later on) changes nothing.
    assert await run_like_arq(deps, new.id, max_tries=NOTIFY_MAX_TRIES) == ("duplicate", [])
    assert send.call_count == 6
    await telegram_http.aclose()
