import asyncio

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.support.containers import alembic_config
from trainsync.db.models import Base

pytestmark = pytest.mark.integration

TABLES = {
    "athletes",
    "oauth_tokens",
    "activities",
    "sync_runs",
    "webhook_events",
    "notifications",
    "exercises",
    "programs",
    "program_days",
    "program_exercises",
    "workouts",
    "workout_sets",
    "body_metrics",
    "foods",
    "food_logs",
    "nutrition_profile",
    "daily_checkins",
}


async def _table_names(url: str) -> set[str]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    finally:
        await engine.dispose()
    return set(names) - {"alembic_version"}


def test_upgrade_downgrade_upgrade_round_trip(pg_url: str) -> None:
    config = alembic_config(pg_url)
    assert asyncio.run(_table_names(pg_url)) == TABLES

    command.downgrade(config, "base")
    assert asyncio.run(_table_names(pg_url)) == set()

    command.upgrade(config, "head")
    assert asyncio.run(_table_names(pg_url)) == TABLES


def _diff(conn: Connection) -> list[object]:
    return list(compare_metadata(MigrationContext.configure(conn), Base.metadata))


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        diff = await conn.run_sync(_diff)
    assert diff == []


async def test_expected_indexes_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        activity_ix = await conn.run_sync(lambda c: inspect(c).get_indexes("activities"))
        webhook_ix = await conn.run_sync(lambda c: inspect(c).get_indexes("webhook_events"))
    by_name = {ix["name"]: ix for ix in [*activity_ix, *webhook_ix]}
    assert by_name["ix_activities_athlete_start_date"]["column_names"] == [
        "athlete_id",
        "start_date",
    ]
    assert by_name["ix_activities_athlete_start_date"].get("column_sorting") == {
        "start_date": ("desc",)
    }
    assert by_name["ix_activities_athlete_sport_start_date"]["column_names"] == [
        "athlete_id",
        "sport_type",
        "start_date",
    ]
    assert by_name["ix_webhook_events_status_received_at"]["column_names"] == [
        "status",
        "received_at",
    ]
