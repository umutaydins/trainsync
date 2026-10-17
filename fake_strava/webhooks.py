"""Pushes Strava-style webhook events at a target URL, imitating Strava's delivery.

Strava gives a subscriber 2 seconds to answer 200 and retries a failed delivery a few times.
The sender does the same (timeout, up to `max_attempts` tries per delivery) and can repeat
events (`duplicate`, like Strava retries that do reach us) or shuffle them (`out_of_order`).
"""

import asyncio
import random
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

DeliveryMode = Literal["single", "duplicate", "out_of_order"]
DEFAULT_TIMEOUT_S = 2.0
DEFAULT_MAX_ATTEMPTS = 3  # the first try + 2 retries


class WebhookEvent(BaseModel):
    object_type: Literal["activity", "athlete"]
    object_id: int
    aspect_type: Literal["create", "update", "delete"]
    updates: dict[str, Any] = Field(default_factory=dict)
    owner_id: int
    subscription_id: int
    event_time: int


class FireRequest(BaseModel):
    target_url: str
    events: list[WebhookEvent]
    mode: DeliveryMode = "single"
    duplicates: int = Field(default=3, ge=1, le=20)
    concurrency: int = Field(default=1, ge=1, le=100)
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, le=10)


class Attempt(BaseModel):
    status: int | None
    latency_ms: float
    error: str | None = None


class Delivery(BaseModel):
    event_index: int
    event: WebhookEvent
    attempts: list[Attempt]

    @property
    def delivered(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].status == 200


class DeliveryReport(BaseModel):
    deliveries: list[Delivery]
    delivered: int
    failed: int


def plan(request: FireRequest, rng: random.Random) -> list[tuple[int, WebhookEvent]]:
    """The deliveries in sending order, as (index into `request.events`, event)."""
    indexed = list(enumerate(request.events))
    if request.mode == "duplicate":
        return [item for item in indexed for _ in range(request.duplicates)]
    if request.mode == "out_of_order" and len(indexed) > 1:
        original = list(indexed)
        while indexed == original:  # "out of order" must not be the original order
            rng.shuffle(indexed)
    return indexed


async def fire(request: FireRequest, http: httpx.AsyncClient, rng: random.Random) -> DeliveryReport:
    semaphore = asyncio.Semaphore(request.concurrency)

    async def deliver(index: int, event: WebhookEvent) -> Delivery:
        async with semaphore:
            attempts = await _deliver(http, request, event)
        return Delivery(event_index=index, event=event, attempts=attempts)

    deliveries = await asyncio.gather(*(deliver(i, e) for i, e in plan(request, rng)))
    delivered = sum(1 for d in deliveries if d.delivered)
    return DeliveryReport(
        deliveries=list(deliveries), delivered=delivered, failed=len(deliveries) - delivered
    )


async def _deliver(
    http: httpx.AsyncClient, request: FireRequest, event: WebhookEvent
) -> list[Attempt]:
    attempts: list[Attempt] = []
    body = event.model_dump(mode="json")
    for _ in range(request.max_attempts):
        started = time.perf_counter()
        try:
            # wait_for, not httpx timeouts: those don't apply to in-process ASGI targets.
            response = await asyncio.wait_for(
                http.post(request.target_url, json=body), request.timeout_s
            )
        except (TimeoutError, httpx.TransportError) as exc:
            attempts.append(Attempt(status=None, latency_ms=_ms(started), error=type(exc).__name__))
            continue
        attempts.append(Attempt(status=response.status_code, latency_ms=_ms(started)))
        if response.status_code == 200:
            break
    return attempts


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
