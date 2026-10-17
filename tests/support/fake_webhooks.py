"""Typed helpers around fake_strava's webhook control endpoints."""

from typing import Any, Literal

import httpx

from fake_strava.app import ScenarioResponse
from fake_strava.webhooks import DeliveryReport, WebhookEvent

Mode = Literal["single", "duplicate", "out_of_order"]


def activity_event(
    activity_id: int,
    aspect: Literal["create", "update", "delete"],
    *,
    owner_id: int,
    subscription_id: int,
    event_time: int,
    updates: dict[str, Any] | None = None,
) -> WebhookEvent:
    return WebhookEvent(
        object_type="activity",
        object_id=activity_id,
        aspect_type=aspect,
        updates=updates or {},
        owner_id=owner_id,
        subscription_id=subscription_id,
        event_time=event_time,
    )


async def fire(
    fake: httpx.AsyncClient,
    target_url: str,
    events: list[WebhookEvent],
    *,
    mode: Mode = "single",
    duplicates: int = 3,
    concurrency: int = 1,
    timeout_s: float = 2.0,
    max_attempts: int = 3,
) -> DeliveryReport:
    response = await fake.post(
        "/_control/webhooks/fire",
        json={
            "target_url": target_url,
            "events": [e.model_dump(mode="json") for e in events],
            "mode": mode,
            "duplicates": duplicates,
            "concurrency": concurrency,
            "timeout_s": timeout_s,
            "max_attempts": max_attempts,
        },
    )
    response.raise_for_status()
    return DeliveryReport.model_validate(response.json())


async def activity_lifecycle(
    fake: httpx.AsyncClient,
    target_url: str,
    *,
    out_of_order: bool = False,
    delete: bool = True,
    title: str = "Renamed by the athlete",
    subscription_id: int | None = None,
) -> ScenarioResponse:
    response = await fake.post(
        "/_control/scenario/activity-lifecycle",
        json={
            "target_url": target_url,
            "out_of_order": out_of_order,
            "delete": delete,
            "title": title,
            "subscription_id": subscription_id,
        },
    )
    response.raise_for_status()
    return ScenarioResponse.model_validate(response.json())


async def deauthorize(
    fake: httpx.AsyncClient, target_url: str, *, subscription_id: int | None = None
) -> ScenarioResponse:
    response = await fake.post(
        "/_control/scenario/deauthorize",
        json={"target_url": target_url, "subscription_id": subscription_id},
    )
    response.raise_for_status()
    return ScenarioResponse.model_validate(response.json())
