"""`webhook_events` rows: deduplicated inbox for Strava push events.

Status flow (docs/diagrams.md §12): `pending → processing → processed`; a deferral puts the row
back to `pending`, an error to `failed`, which the retry cron picks up again.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.db.models import WebhookEvent, WebhookStatus

_CLAIMABLE = (WebhookStatus.PENDING, WebhookStatus.FAILED)
MAX_ATTEMPTS = 8
MAX_BACKOFF = timedelta(hours=6)


def backoff(attempts: int) -> timedelta:
    """Wait after the `attempts`-th failed try: 2, 4, 8 … minutes, capped at 6 hours."""
    return min(timedelta(minutes=2**attempts), MAX_BACKOFF)


def next_retry_at(event: WebhookEvent) -> datetime:
    last = event.last_attempt_at or event.received_at
    return last + backoff(event.attempts)


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

    async def claim(self, event_id: int, now: datetime) -> WebhookEvent | None:
        """`pending|failed → processing`, `attempts + 1`; `None` if someone else has it or it is
        already processed."""
        stmt = (
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id, WebhookEvent.status.in_(_CLAIMABLE))
            .values(
                status=WebhookStatus.PROCESSING,
                attempts=WebhookEvent.attempts + 1,
                last_attempt_at=now,
            )
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

    async def retry_candidates(
        self, now: datetime, *, stale_after: timedelta, limit: int
    ) -> list[WebhookEvent]:
        """Events the retry cron should look at, oldest first:
        - `failed` with attempts left (the backoff is checked by the caller);
        - `pending` received more than `stale_after` ago (their job may have been lost);
        - `processing` claimed more than `stale_after` ago (their worker died)."""
        stale = now - stale_after
        stmt = (
            select(WebhookEvent)
            .where(
                or_(
                    and_(
                        WebhookEvent.status == WebhookStatus.FAILED,
                        WebhookEvent.attempts < MAX_ATTEMPTS,
                    ),
                    and_(
                        WebhookEvent.status == WebhookStatus.PENDING,
                        WebhookEvent.received_at < stale,
                    ),
                    and_(
                        WebhookEvent.status == WebhookStatus.PROCESSING,
                        WebhookEvent.last_attempt_at < stale,
                    ),
                )
            )
            .order_by(WebhookEvent.received_at)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def release_stuck(self, event_id: int, claimed_at: datetime | None) -> bool:
        """`processing → failed` for an event whose worker died, unless it was claimed again."""
        result = await self._session.execute(
            update(WebhookEvent)
            .where(
                WebhookEvent.id == event_id,
                WebhookEvent.status == WebhookStatus.PROCESSING,
                WebhookEvent.last_attempt_at == claimed_at,
            )
            .values(status=WebhookStatus.FAILED)
            .returning(WebhookEvent.id)
        )
        return result.first() is not None

    async def count_dead(self) -> int:
        count: int | None = await self._session.scalar(
            select(func.count())
            .select_from(WebhookEvent)
            .where(
                WebhookEvent.status == WebhookStatus.FAILED,
                WebhookEvent.attempts >= MAX_ATTEMPTS,
            )
        )
        return count or 0
