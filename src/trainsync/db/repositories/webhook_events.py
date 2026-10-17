"""`webhook_events` rows: deduplicated inbox for Strava push events.

Status flow (docs/diagrams.md §12): `pending → processing → processed`; a deferral puts the row
back to `pending`, an error to `failed`, which the retry cron picks up again.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import WebhookEvent, WebhookStatus

_CLAIMABLE = (WebhookStatus.PENDING, WebhookStatus.FAILED)


class WebhookEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_new(self, dedup_key: str, payload: dict[str, Any]) -> int | None:
        """Store the event; `None` when an event with this dedup key already exists."""
        stmt = (
            insert(WebhookEvent)
            .values(dedup_key=dedup_key, payload=payload)
            .on_conflict_do_nothing(index_elements=[WebhookEvent.dedup_key])
            .returning(WebhookEvent.id)
        )
        event_id: int | None = await self._session.scalar(stmt)
        return event_id

    async def claim(self, event_id: int) -> WebhookEvent | None:
        """`pending|failed → processing`, `attempts + 1`; `None` if someone else has it or it is
        already processed."""
        stmt = (
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id, WebhookEvent.status.in_(_CLAIMABLE))
            .values(status=WebhookStatus.PROCESSING, attempts=WebhookEvent.attempts + 1)
            .returning(WebhookEvent)
        )
        event: WebhookEvent | None = await self._session.scalar(stmt)
        return event

    async def set_status(
        self, event_id: int, status: WebhookStatus, *, processed_at: datetime | None = None
    ) -> None:
        await self._session.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status=status, processed_at=processed_at)
        )

    async def get(self, event_id: int) -> WebhookEvent | None:
        event: WebhookEvent | None = await self._session.scalar(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return event
