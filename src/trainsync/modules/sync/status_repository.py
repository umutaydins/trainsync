"""Sync health reads: a user's newest runs, and the application-wide webhook queue and
freshness (one Strava application serves every user, so those are shared facts)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.strava.models import Athlete
from trainsync.modules.sync.models import SyncRun, SyncStatus, WebhookEvent
from trainsync.modules.sync.webhook_repository import MAX_ATTEMPTS


@dataclass(frozen=True, slots=True)
class WebhookSummary:
    last_received_at: datetime | None
    last_processed_at: datetime | None
    pending: int
    processing: int
    failed: int  # will be retried
    dead_letters: int  # attempts exhausted


class SyncStatusRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def latest_runs(self, athlete_ids: Sequence[int]) -> dict[tuple[int, str], SyncRun]:
        """The newest run per (athlete, kind)."""
        if not athlete_ids:
            return {}
        newest = (
            select(func.max(SyncRun.id))
            .where(SyncRun.user_id == self._user_id, SyncRun.athlete_id.in_(athlete_ids))
            .group_by(SyncRun.athlete_id, SyncRun.kind)
        )
        runs = await self._session.scalars(select(SyncRun).where(SyncRun.id.in_(newest)))
        return {(run.athlete_id, run.kind): run for run in runs}

    async def webhook_summary(self) -> WebhookSummary:
        """Application-wide: webhook events are not tied to a user until processed."""
        received, processed = (
            await self._session.execute(
                select(func.max(WebhookEvent.received_at), func.max(WebhookEvent.processed_at))
            )
        ).one()
        by_status = await self._session.execute(
            select(WebhookEvent.status, func.count()).group_by(WebhookEvent.status)
        )
        counts: dict[str, int] = {status: count for status, count in by_status.all()}
        dead = await self._session.scalar(
            select(func.count())
            .select_from(WebhookEvent)
            .where(WebhookEvent.status == "failed", WebhookEvent.attempts >= MAX_ATTEMPTS)
        )
        return WebhookSummary(
            last_received_at=received,
            last_processed_at=processed,
            pending=counts.get("pending", 0),
            processing=counts.get("processing", 0),
            failed=counts.get("failed", 0) - (dead or 0),
            dead_letters=dead or 0,
        )


async def system_freshness(session: AsyncSession) -> tuple[bool, datetime | None]:
    """For the owner's stack alerts (ADR 0027): is any athlete connected, and the newest
    successful sync or activity write across every user."""
    active = await session.scalar(select(func.count()).select_from(Athlete).where(Athlete.active))
    run_done = await session.scalar(
        select(func.max(SyncRun.finished_at))
        .join(Athlete, Athlete.id == SyncRun.athlete_id)
        .where(Athlete.active, SyncRun.status == SyncStatus.SUCCEEDED)
    )
    written = await session.scalar(
        select(func.max(Activity.synced_at))
        .join(Athlete, Athlete.id == Activity.athlete_id)
        .where(Athlete.active)
    )
    present = [v for v in (run_done, written) if v is not None]
    return bool(active), max(present) if present else None
