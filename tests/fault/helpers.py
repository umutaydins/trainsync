"""Small helpers shared by the fault-injection modules."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from prometheus_client import REGISTRY
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fake_strava.state import FakeStravaState
from trainsync.db.models import Activity, WebhookEvent
from trainsync.sync.webhooks import WebhookDeps, process_event

LIST = "GET /api/v3/athlete/activities"
GET_ACTIVITY = "GET /api/v3/activities/{activity_id}"
TOKEN = "POST /oauth/token"


@dataclass
class ManualClock:
    now: datetime = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def fake_calls(fake: FakeStravaState, endpoint: str, status: str | None = None) -> int:
    by_status = fake.stats_json()["requests"].get(endpoint, {})
    if status is not None:
        return int(by_status.get(status, 0))
    return int(sum(by_status.values()))


def metric(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def visible_activities(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[int, str]:
    """Strava id → name of every activity a reader would see."""
    async with sessionmaker() as session:
        rows = await session.execute(
            select(Activity.strava_activity_id, Activity.name).where(Activity.deleted_at.is_(None))
        )
        return {sid: name for sid, name in rows.all()}


async def count_activities(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(Activity)) or 0


async def drain_webhooks(
    deps: WebhookDeps, sessionmaker: async_sessionmaker[AsyncSession]
) -> list[str]:
    """Play the worker: process pending events in arrival order."""
    async with sessionmaker() as session:
        ids = (
            await session.scalars(
                select(WebhookEvent.id)
                .where(WebhookEvent.status == "pending")
                .order_by(WebhookEvent.id)
            )
        ).all()
    return [(await process_event(deps, event_id)).status for event_id in ids]
