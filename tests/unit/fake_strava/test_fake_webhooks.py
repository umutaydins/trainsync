import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request, Response

from fake_strava.app import create_app
from fake_strava.clock import FakeClock
from fake_strava.config import FakeStravaConfig
from fake_strava.state import FakeStravaState
from tests.conftest import fake_strava_login
from tests.support import fake_webhooks
from tests.support.fake_webhooks import activity_event

TARGET = "http://target/hook"


@dataclass
class Target:
    """A dummy subscriber: records bodies, answers from a script (status or 'slow')."""

    script: list[int | str] = field(default_factory=list)
    received: list[dict[str, Any]] = field(default_factory=list)
    slow_s: float = 0.5

    def app(self) -> FastAPI:
        app = FastAPI()

        @app.post("/hook")
        async def hook(request: Request) -> Response:
            self.received.append(await request.json())
            step = self.script.pop(0) if self.script else 200
            if step == "slow":
                await asyncio.sleep(self.slow_s)
                step = 200
            return Response(status_code=int(step))

        return app


@pytest.fixture
def target() -> Target:
    return Target()


@pytest.fixture
async def fake(target: Target) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        FakeStravaConfig(seed_activities=3), FakeClock(), httpx.ASGITransport(app=target.app())
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fake"
    ) as client:
        client.state = app.state.fake  # type: ignore[attr-defined]
        yield client


def _events(n: int) -> list[Any]:
    return [
        activity_event(i, "update", owner_id=1, subscription_id=1, event_time=1000 + i)
        for i in range(1, n + 1)
    ]


async def test_single_mode_delivers_each_event_once_in_order(
    fake: httpx.AsyncClient, target: Target
) -> None:
    report = await fake_webhooks.fire(fake, TARGET, _events(4))
    assert [b["object_id"] for b in target.received] == [1, 2, 3, 4]
    assert (report.delivered, report.failed) == (4, 0)
    assert all(len(d.attempts) == 1 and d.attempts[0].status == 200 for d in report.deliveries)


async def test_duplicate_mode_repeats_each_event(fake: httpx.AsyncClient, target: Target) -> None:
    report = await fake_webhooks.fire(fake, TARGET, _events(2), mode="duplicate", duplicates=3)
    assert [b["object_id"] for b in target.received] == [1, 1, 1, 2, 2, 2]
    assert report.delivered == 6


async def test_out_of_order_mode_shuffles_deterministically(target: Target) -> None:
    orders = []
    for _ in range(2):
        target.received.clear()
        app = create_app(
            FakeStravaConfig(seed_activities=0), FakeClock(), httpx.ASGITransport(app=target.app())
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://fake") as client:
            await fake_webhooks.fire(client, TARGET, _events(5), mode="out_of_order")
        orders.append([b["object_id"] for b in target.received])
    assert orders[0] == orders[1]  # seeded
    assert sorted(orders[0]) == [1, 2, 3, 4, 5]
    assert orders[0] != [1, 2, 3, 4, 5]


async def test_retries_on_500_until_200(fake: httpx.AsyncClient, target: Target) -> None:
    target.script = [500, 503]
    report = await fake_webhooks.fire(fake, TARGET, _events(1))
    (delivery,) = report.deliveries
    assert [a.status for a in delivery.attempts] == [500, 503, 200]
    assert delivery.delivered


async def test_gives_up_after_three_attempts(fake: httpx.AsyncClient, target: Target) -> None:
    target.script = [500, 500, 500, 500]
    report = await fake_webhooks.fire(fake, TARGET, _events(1))
    (delivery,) = report.deliveries
    assert [a.status for a in delivery.attempts] == [500, 500, 500]
    assert (report.delivered, report.failed) == (0, 1)


async def test_retries_a_slow_target(fake: httpx.AsyncClient, target: Target) -> None:
    target.script = ["slow"]
    report = await fake_webhooks.fire(fake, TARGET, _events(1), timeout_s=0.05)
    (delivery,) = report.deliveries
    assert [a.status for a in delivery.attempts] == [None, 200]
    assert delivery.attempts[0].error == "TimeoutError"
    assert len(target.received) == 2


async def test_concurrency_sends_in_parallel(fake: httpx.AsyncClient, target: Target) -> None:
    target.script = ["slow"] * 4
    target.slow_s = 0.2
    loop = asyncio.get_running_loop()
    started = loop.time()
    report = await fake_webhooks.fire(fake, TARGET, _events(4), concurrency=4)
    assert report.delivered == 4
    assert loop.time() - started < 0.6


async def test_lifecycle_scenario_matches_fake_state(
    fake: httpx.AsyncClient, target: Target
) -> None:
    state: FakeStravaState = fake.state  # type: ignore[attr-defined]
    kept = await fake_webhooks.activity_lifecycle(fake, TARGET, delete=False, title="Hill reps")
    assert kept.activity_id is not None
    assert state.activities[kept.activity_id].name == "Hill reps"
    assert [e.aspect_type for e in kept.events] == ["create", "update"]

    target.received.clear()
    gone = await fake_webhooks.activity_lifecycle(fake, TARGET, out_of_order=True)
    assert gone.activity_id is not None
    assert gone.activity_id not in state.activities
    assert [e.aspect_type for e in gone.events] == ["create", "update", "delete"]
    times = [e.event_time for e in gone.events]
    assert times == sorted(times)
    assert len(set(times)) == 3
    sent = [b["aspect_type"] for b in target.received]
    assert sorted(sent) == ["create", "delete", "update"]
    assert sent != ["create", "update", "delete"]
    assert {(e.owner_id, e.subscription_id) for e in gone.events} == {(state.default_athlete_id, 1)}


async def test_deauthorize_scenario_revokes_tokens_and_fires_event(
    fake: httpx.AsyncClient, target: Target
) -> None:
    state: FakeStravaState = fake.state  # type: ignore[attr-defined]
    token: str = (await fake_strava_login(fake))["access_token"]
    assert state.authenticate(token) is not None
    result = await fake_webhooks.deauthorize(fake, TARGET, subscription_id=999)
    assert state.authenticate(token) is None
    (event,) = target.received
    assert event["object_type"] == "athlete"
    assert event["aspect_type"] == "update"
    assert event["updates"] == {"authorized": "false"}
    assert event["subscription_id"] == 999
    assert result.report.delivered == 1
