"""Strava webhook endpoints: subscription validation and ack-then-enqueue event intake.

The POST handler only validates, persists (deduplicated) and enqueues. It never calls Strava:
Strava wants a 200 within 2 seconds, and the worker does the fetching (ADR 0006).
"""

import hashlib
import hmac
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trainsync.core.deps import JobQueueDep, SessionmakerDep, SettingsDep
from trainsync.core.errors import error
from trainsync.core.logging import get_logger
from trainsync.core.metrics import WEBHOOK_EVENTS, webhook_aspect
from trainsync.modules.sync.webhook_repository import WebhookEventRepository

router = APIRouter(prefix="/webhooks/strava", tags=["webhooks"])
log = get_logger(__name__)

EXAMPLE_EVENT: dict[str, Any] = {
    "object_type": "activity",
    "object_id": 1360128428,
    "aspect_type": "update",
    "updates": {"title": "Morning Run"},
    "owner_id": 134815,
    "subscription_id": 120475,
    "event_time": 1516126040,
}


class StravaEvent(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [EXAMPLE_EVENT]})

    object_type: Literal["activity", "athlete"]
    object_id: int
    aspect_type: Literal["create", "update", "delete"]
    updates: dict[str, Any] = Field(default_factory=dict)
    owner_id: int
    subscription_id: int
    event_time: int

    def dedup_key(self) -> str:
        """Strava retries resend the identical event; these five fields identify it."""
        raw = (
            f"{self.subscription_id}:{self.object_type}:{self.object_id}:"
            f"{self.aspect_type}:{self.event_time}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()


class ChallengeResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"examples": [{"hub.challenge": "15f7d1a91c1f40f8a748fd134752feb3"}]},
    )

    challenge: str = Field(alias="hub.challenge")


class Ack(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "queued"}]})

    status: Literal["queued", "duplicate", "ignored"]


@router.get(
    "",
    summary="Webhook subscription validation",
    description=(
        "Strava calls this once when the subscription is created. Echoes `hub.challenge` when "
        "`hub.mode=subscribe` and `hub.verify_token` matches `STRAVA_WEBHOOK_VERIFY_TOKEN`."
    ),
    response_model=ChallengeResponse,
    response_model_by_alias=True,
    responses={403: error("Wrong mode or verify token", "verification failed")},
)
async def validate_subscription(
    settings: SettingsDep,
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
    verify_token: Annotated[str, Query(alias="hub.verify_token")] = "",
) -> ChallengeResponse:
    expected = settings.strava_webhook_verify_token.get_secret_value()
    if mode != "subscribe" or not hmac.compare_digest(verify_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verification failed")
    return ChallengeResponse.model_validate({"hub.challenge": challenge})


@router.post(
    "",
    summary="Receive a Strava webhook event",
    description=(
        "Validates the event, stores it once (deduplicated on subscription, object, aspect and "
        "event time) and enqueues `process_webhook_event`. Always answers 200 for a well-formed "
        "event, including duplicates and events for another subscription, so Strava does not "
        "retry. No Strava call happens here."
    ),
    response_model=Ack,
    responses={400: error("Body is not a valid Strava event", "invalid webhook event")},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": StravaEvent.model_json_schema(),
                    "example": EXAMPLE_EVENT,
                }
            },
        }
    },
)
async def receive_event(
    request: Request,
    settings: SettingsDep,
    sessionmaker: SessionmakerDep,
    queue: JobQueueDep,
) -> Ack:
    event = await _parse_event(request)
    expected_sub = settings.strava_webhook_subscription_id
    if expected_sub is not None and event.subscription_id != expected_sub:
        log.warning("webhook_wrong_subscription", subscription_id=event.subscription_id)
        return _ack(event, "ignored")

    async with sessionmaker.begin() as session:
        event_id = await WebhookEventRepository(session).insert_new(
            event.dedup_key(), event.model_dump(mode="json")
        )
    if event_id is None:
        log.info("webhook_duplicate", object_type=event.object_type, object_id=event.object_id)
        return _ack(event, "duplicate")
    try:
        await queue.enqueue_webhook_event(event_id)
    except Exception:
        # Stored but not queued: the retry cron sweeps stale `pending` events (P3.4). Answering
        # 500 would not help, because Strava's retry is a duplicate and enqueues nothing.
        log.exception("webhook_enqueue_failed", event_id=event_id)
    log.info(
        "webhook_received",
        event_id=event_id,
        object_type=event.object_type,
        aspect_type=event.aspect_type,
    )
    return _ack(event, "queued")


def _ack(event: StravaEvent, status: Literal["queued", "duplicate", "ignored"]) -> Ack:
    WEBHOOK_EVENTS.labels(webhook_aspect(event.object_type, event.aspect_type), status).inc()
    return Ack(status=status)


async def _parse_event(request: Request) -> StravaEvent:
    body = await request.body()
    try:
        return StravaEvent.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid webhook event") from exc
