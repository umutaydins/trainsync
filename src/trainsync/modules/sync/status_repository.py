"""Sync health reads: the newest run per athlete and kind, and the webhook queue's state."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.sync.models import SyncRun, WebhookEvent
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
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_runs(self, athlete_ids: Sequence[int]) -> dict[tuple[int, str], SyncRun]:
        """The newest run per (athlete, kind)."""
        if not athlete_ids:
            return {}
        newest = (
            select(func.max(SyncRun.id))
            .where(SyncRun.athlete_id.in_(athlete_ids))
            .group_by(SyncRun.athlete_id, SyncRun.kind)
        )
        runs = await self._session.scalars(select(SyncRun).where(SyncRun.id.in_(newest)))
        return {(run.athlete_id, run.kind): run for run in runs}

    async def webhook_summary(self) -> WebhookSummary:
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
