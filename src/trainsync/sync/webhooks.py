"""Processing stored webhook events (`process_webhook_event` job).

Activity create/update events fetch the activity's *current* state from Strava and upsert it.
The event payload is only a trigger, so duplicates and out-of-order delivery converge on the
latest state (ADR 0007). A 404 on fetch means the activity is gone: soft delete.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from arq.worker import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import Clock
from trainsync.core.logging import get_logger
from trainsync.db.models import WebhookStatus
from trainsync.db.repositories.activities import ActivityRepository
from trainsync.db.repositories.athletes import AthleteRepository
from trainsync.db.repositories.webhook_events import WebhookEventRepository
from trainsync.strava.budget import Priority
from trainsync.strava.errors import CircuitOpen, RateLimited, StravaNotFound
from trainsync.strava.models import StravaActivity
from trainsync.sync.common import SYNC_MAX_TRIES, retry_after, short_error
from trainsync.sync.context import worker_context

log = get_logger(__name__)


class ActivityFetcher(Protocol):
    async def get_activity(
        self, athlete_id: int, activity_id: int, *, priority: Priority = "low"
    ) -> StravaActivity: ...


@dataclass(frozen=True, slots=True)
class WebhookDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    strava: ActivityFetcher
    clock: Clock


@dataclass(frozen=True, slots=True)
class WebhookOutcome:
    """`status` is what happened: processed / ignored / skipped / deferred / failed."""

    status: str
    resume_at: datetime | None = None


async def process_event(deps: WebhookDeps, event_id: int) -> WebhookOutcome:
    async with deps.sessionmaker.begin() as session:
        event = await WebhookEventRepository(session).claim(event_id, deps.clock())
    if event is None:
        return WebhookOutcome("skipped")  # already processed, or another worker has it

    try:
        status = await _apply(deps, event.payload)
    except (RateLimited, CircuitOpen) as exc:
        resume_at = exc.reset_at if isinstance(exc, RateLimited) else exc.retry_at
        await _set(deps, event_id, WebhookStatus.PENDING)
        log.info("webhook_deferred", event_id=event_id, resume_at=resume_at)
        return WebhookOutcome("deferred", resume_at)
    except asyncio.CancelledError:
        await _set(deps, event_id, WebhookStatus.PENDING)  # worker shutdown: try again later
        raise
    except Exception as exc:
        await _set(deps, event_id, WebhookStatus.FAILED)
        log.warning(
            "webhook_failed", event_id=event_id, attempts=event.attempts, error=short_error(exc)
        )
        return WebhookOutcome("failed")
    await _set(deps, event_id, WebhookStatus.PROCESSED, processed_at=deps.clock())
    log.info("webhook_processed", event_id=event_id, outcome=status)
    return WebhookOutcome(status)


async def _apply(deps: WebhookDeps, payload: dict[str, Any]) -> str:
    object_type = payload["object_type"]
    aspect = payload["aspect_type"]
    async with deps.sessionmaker() as session:
        athlete = await AthleteRepository(session).by_strava_id(int(payload["owner_id"]))
    if athlete is None:
        log.info("webhook_unknown_owner", owner_id=payload["owner_id"])
        return "ignored"

    if object_type == "athlete":
        if aspect == "update" and str(payload.get("updates", {}).get("authorized")) == "false":
            return await _deauthorize(deps, athlete.id)
        return "ignored"
    if not athlete.active:
        return "ignored"  # deauthorized: nothing of theirs is fetched or stored any more

    activity_id = int(payload["object_id"])
    if aspect == "delete":
        return await _soft_delete(deps, activity_id)
    try:
        activity = await deps.strava.get_activity(athlete.id, activity_id, priority="high")
    except StravaNotFound:
        return await _soft_delete(deps, activity_id)
    async with deps.sessionmaker.begin() as session:
        if not await AthleteRepository(session).is_active_locked(athlete.id):
            return "ignored"
        await ActivityRepository(session).upsert_many(athlete.id, [activity])
    return "upserted"


async def _soft_delete(deps: WebhookDeps, activity_id: int) -> str:
    async with deps.sessionmaker.begin() as session:
        await ActivityRepository(session).soft_delete(activity_id)
    return "deleted"


async def _deauthorize(deps: WebhookDeps, athlete_id: int) -> str:
    async with deps.sessionmaker.begin() as session:
        removed = await AthleteRepository(session).deauthorize(athlete_id)
    log.info("athlete_deauthorized", athlete_id=athlete_id, activities_removed=removed)
    return "deauthorized"


async def _set(
    deps: WebhookDeps,
    event_id: int,
    status: WebhookStatus,
    *,
    processed_at: datetime | None = None,
) -> None:
    async with deps.sessionmaker.begin() as session:
        await WebhookEventRepository(session).set_status(
            event_id, status, processed_at=processed_at
        )


async def process_webhook_event(ctx: dict[str, Any], event_id: int) -> str:
    wc = worker_context(ctx)
    outcome = await process_event(WebhookDeps(wc.sessionmaker, wc.strava, wc.clock), event_id)
    retry = retry_after(outcome.resume_at, wc.clock())
    if retry is not None:
        raise retry
    return outcome.status


process_webhook_event_job = func(
    process_webhook_event, name="process_webhook_event", max_tries=SYNC_MAX_TRIES
)
