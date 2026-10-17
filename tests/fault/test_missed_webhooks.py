"""Failure mode: missed webhooks → the incremental sync with its 2-day overlap window catches up.

After a full backfill, the athlete edits a recent activity and uploads one dated a day back.
No webhook arrives. The next incremental run picks up both, and only asks Strava for the
window, not the whole history.
"""

from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from tests.fault.helpers import LIST, ManualClock, fake_calls, visible_activities
from tests.support.factories import create_athlete
from tests.support.strava import fake_backed_client
from trainsync.core.settings import Settings
from trainsync.strava.budget import UnlimitedBudget
from trainsync.sync.backfill import run_backfill
from trainsync.sync.context import SyncDeps
from trainsync.sync.incremental import run_incremental


async def test_incremental_sync_catches_changes_without_webhooks(
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_strava: FakeStravaState,
    fake_strava_client: httpx.AsyncClient,
    fake_strava_token: dict[str, Any],
    integration_settings: Settings,
) -> None:
    athlete_id = await create_athlete(sessionmaker, fake_strava.default_athlete_id)
    strava = fake_backed_client(
        fake_strava_client, integration_settings, fake_strava_token["access_token"]
    )
    deps = SyncDeps(sessionmaker, strava, UnlimitedBudget(), ManualClock())
    assert (await run_backfill(deps, athlete_id)).status == "succeeded"

    newest = max(fake_strava.activities.values(), key=lambda a: a.start_date)
    await fake_strava_client.post(
        "/_control/activities",
        json={"action": "update", "id": newest.id, "fields": {"name": "Edited later"}},
    )
    late = (newest.start_date - timedelta(days=1)).isoformat()
    created = await fake_strava_client.post(
        "/_control/activities",
        json={
            "action": "create",
            "id": 77_777,
            "fields": {"name": "Late upload", "start_date": late},
        },
    )
    created.raise_for_status()

    calls_before = fake_calls(fake_strava, LIST)
    assert (await run_incremental(deps, athlete_id)).status == "succeeded"

    visible = await visible_activities(sessionmaker)
    assert visible[newest.id] == "Edited later"
    assert visible[77_777] == "Late upload"
    assert set(visible) == set(fake_strava.activities)
    assert fake_calls(fake_strava, LIST) - calls_before <= 2  # one page + the empty end
