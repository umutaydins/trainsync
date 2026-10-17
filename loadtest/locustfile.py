"""Load test: Strava-style webhook POSTs and the read API.

Run through `make loadtest`, which starts the compose stack, connects an athlete, waits for the
backfill and then runs locust headless. Environment:
- `LOADTEST_API_KEY` (default `dev-key-1`, the compose stack's key)
- `LOADTEST_OWNER_ID`: Strava athlete id used as `owner_id` in events
- `LOADTEST_SUBSCRIPTION_ID` (default 1, matches compose)
"""

import itertools
import os
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from locust import HttpUser, between, task

API_KEY = os.environ.get("LOADTEST_API_KEY", "dev-key-1")
OWNER_ID = int(os.environ.get("LOADTEST_OWNER_ID", "1"))
SUBSCRIPTION_ID = int(os.environ.get("LOADTEST_SUBSCRIPTION_ID", "1"))
DUPLICATE_SHARE = 0.10
FIRST_ACTIVITY_ID = 10_000_000_000

_event_times = itertools.count(int(time.time()) * 1000)


def _new_event() -> dict[str, Any]:
    aspect = random.choices(["create", "update", "delete"], weights=[3, 6, 1])[0]
    return {
        "object_type": "activity",
        "object_id": FIRST_ACTIVITY_ID + random.randrange(5000),
        "aspect_type": aspect,
        "updates": {"title": "Evening run"} if aspect == "update" else {},
        "owner_id": OWNER_ID,
        "subscription_id": SUBSCRIPTION_ID,
        "event_time": next(_event_times),
    }


class WebhookSender(HttpUser):
    """Strava pushing events; about 10% are re-deliveries of an event already sent."""

    wait_time = between(0.05, 0.2)

    def on_start(self) -> None:
        self.sent: list[dict[str, Any]] = []

    @task
    def post_event(self) -> None:
        if self.sent and random.random() < DUPLICATE_SHARE:
            event = random.choice(self.sent)
            name = "POST /webhooks/strava (duplicate)"
        else:
            event = _new_event()
            self.sent = [*self.sent[-50:], event]
            name = "POST /webhooks/strava"
        self.client.post("/webhooks/strava", json=event, name=name)


class ApiReader(HttpUser):
    """A client reading activities page by page and weekly stats."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.client.headers["X-API-Key"] = API_KEY

    @task(3)
    def browse_activities(self) -> None:
        response = self.client.get(
            "/v1/activities", params={"limit": 50}, name="GET /v1/activities"
        )
        for _ in range(2):
            cursor = response.json().get("next_cursor") if response.ok else None
            if not cursor:
                return
            response = self.client.get(
                "/v1/activities",
                params={"limit": 50, "cursor": cursor},
                name="GET /v1/activities (next page)",
            )

    @task(1)
    def weekly_stats(self) -> None:
        today = datetime.now(UTC).date()
        start = today - timedelta(weeks=random.choice([4, 12, 52]))
        self.client.get(
            "/v1/stats/weekly",
            params={"from": start.isoformat(), "to": today.isoformat()},
            name="GET /v1/stats/weekly",
        )
