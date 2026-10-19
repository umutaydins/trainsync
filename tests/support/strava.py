"""Helpers to build a StravaClient for unit tests (respx-mocked or fake_strava-backed)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from tests.conftest import FAKE_STRAVA_BASE_URL
from trainsync.core.clock import Clock, utc_now
from trainsync.core.settings import Settings
from trainsync.integrations.strava.budget import Allowance, Priority
from trainsync.integrations.strava.client import RateLimitHook, StravaClient
from trainsync.integrations.strava.ratelimit import RateLimitSnapshot

API = "https://strava.test/api/v3"
OAUTH = "https://strava.test/oauth"
NOW = datetime(2026, 10, 17, 12, 7, tzinfo=UTC)


@dataclass
class StubTokens:
    token: str = "access-1"
    refreshed: str = "access-2"
    refresh_calls: int = 0

    async def access_token(self, athlete_id: int) -> str:
        return self.token

    async def force_refresh(self, athlete_id: int) -> str:
        self.refresh_calls += 1
        self.token = self.refreshed
        return self.token


@dataclass
class Recorder:
    """Records sleeps and acts as a permissive rate budget that remembers what it saw."""

    sleeps: list[float] = field(default_factory=list)
    snapshots: list[RateLimitSnapshot] = field(default_factory=list)
    blocked: list[datetime] = field(default_factory=list)
    deny: Allowance | None = None

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    async def allow(self, priority: Priority) -> Allowance:
        return self.deny or Allowance(True)

    async def record(self, snapshot: RateLimitSnapshot) -> None:
        self.snapshots.append(snapshot)

    async def block_until(self, reset_at: datetime) -> None:
        self.blocked.append(reset_at)


def make_client(
    http: httpx.AsyncClient,
    settings: Settings,
    *,
    tokens: StubTokens | None = None,
    recorder: Recorder | None = None,
    now: datetime = NOW,
) -> StravaClient:
    recorder = recorder or Recorder()
    return StravaClient(
        http,
        settings.model_copy(update={"strava_api_base_url": API, "strava_oauth_base_url": OAUTH}),
        tokens or StubTokens(),
        clock=lambda: now,
        sleep=recorder.sleep,
        budget=recorder,
    )


def activity_json(activity_id: int = 1, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": activity_id,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date": "2026-10-01T06:30:00Z",
        "distance": 10012.5,
        "moving_time": 3000,
        "elapsed_time": 3100,
        "total_elevation_gain": 42.0,
        "average_heartrate": 151.2,
        "kudos_count": 3,
    }
    data.update(overrides)
    return data


def fake_backed_client(
    fake_client: httpx.AsyncClient,
    settings: Settings,
    access_token: str,
    *,
    budget: RateLimitHook | None = None,
    clock: Clock = utc_now,
) -> StravaClient:
    """A real StravaClient talking to the in-process fake_strava with a fixed token."""

    async def no_sleep(_: float) -> None:
        return None

    return StravaClient(
        fake_client,
        settings.model_copy(
            update={
                "strava_api_base_url": f"{FAKE_STRAVA_BASE_URL}/api/v3",
                "strava_oauth_base_url": f"{FAKE_STRAVA_BASE_URL}/oauth",
            }
        ),
        StubTokens(token=access_token, refreshed=access_token),
        sleep=no_sleep,
        clock=clock,
        budget=budget,
    )
