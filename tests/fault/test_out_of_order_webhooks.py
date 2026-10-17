"""Failure mode: out-of-order webhook events → the worker always fetches the current state.

Twelve activities go through create → rename (→ delete for half of them). All their events
arrive shuffled and concurrently, then are processed in a second random order. What a reader
sees must equal fake_strava's final state exactly.
"""

import random
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.fault.conftest import API_URL, SUBSCRIPTION
from tests.fault.helpers import visible_activities
from tests.support import fake_webhooks
from tests.support.factories import create_athlete
from tests.support.fake_webhooks import activity_event
from tests.support.strava import fake_backed_client
from trainsync.core.clock import utc_now
from trainsync.core.settings import Settings
from trainsync.db.models import WebhookEvent
from trainsync.sync.webhooks import WebhookDeps, process_event

TARGET = f"{API_URL}/webhooks/strava"
ACTIVITIES = 12


async def test_shuffled_lifecycles_converge_on_strava_state(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    owner = fake_strava.default_athlete_id
    events = []
    touched = []
    for n in range(ACTIVITIES):
        activity_id = 90_000 + n
        touched.append(activity_id)
        for action, fields in (("create", {}), ("update", {"name": f"Session {n}"})):
            response = await fake_strava_client.post(
                "/_control/activities", json={"action": action, "id": activity_id, "fields": fields}
            )
            response.raise_for_status()
        steps = ["create", "update"]
        if n % 2:
            await fake_strava_client.post(
                "/_control/activities", json={"action": "delete", "id": activity_id}
            )
            steps.append("delete")
        events += [
            activity_event(
                activity_id,
                aspect,
                owner_id=owner,
                subscription_id=SUBSCRIPTION,
                event_time=n * 10 + k,
            )
            for k, aspect in enumerate(steps)
        ]

    report = await fake_webhooks.fire(
        fake_strava_client, TARGET, events, mode="out_of_order", concurrency=8
    )
    assert report.delivered == len(events)

    async with sessionmaker() as session:
        ids = list((await session.scalars(select(WebhookEvent.id))).all())
    random.Random(7).shuffle(ids)
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    deps = WebhookDeps(sessionmaker, strava, utc_now)
    for event_id in ids:
        assert (await process_event(deps, event_id)).status in {"upserted", "deleted"}

    visible = await visible_activities(sessionmaker)
    expected = {
        aid: fake_strava.activities[aid].name for aid in touched if aid in fake_strava.activities
    }
    assert {aid: name for aid, name in visible.items() if aid in touched} == expected
    assert len(expected) == ACTIVITIES // 2
