import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.support.containers import alembic_config
from trainsync.modules.models import Base

pytestmark = pytest.mark.integration

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"

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
    "chat_settings",
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


def test_every_reversible_migration_steps_down_and_up_again(pg_url: str) -> None:
    """`reversible = True` (P7.5, ADR 0026) is backed by a downgrade that actually runs: each
    migration, from the head down, downgrades one step and upgrades again cleanly."""
    config = alembic_config(pg_url)
    revisions = sorted(p.name.split("_", 1)[0] for p in VERSIONS.glob("[0-9]*.py"))
    try:
        for revision in reversed(revisions):
            command.downgrade(config, "-1")
            command.upgrade(config, revision)
            command.downgrade(config, "-1")
    finally:
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


def test_0008_backfills_food_log_snapshots_from_the_food(pg_url: str) -> None:
    config = alembic_config(pg_url)
    command.downgrade(config, "0007")
    try:
        asyncio.run(
            _execute(
                pg_url,
                "INSERT INTO foods (id, name, kcal_100g, protein_100g, carbs_100g, fat_100g)"
                " VALUES (1, 'Oats', 380, 13, NULL, 7)",
                "INSERT INTO food_logs (client_id, date, meal, food_id, grams)"
                " VALUES (gen_random_uuid(), '2026-10-13', 'breakfast', 1, 80)",
            )
        )
        command.upgrade(config, "0008")
        rows = asyncio.run(
            _fetch(pg_url, "SELECT kcal_100g, protein_100g, carbs_100g, fat_100g FROM food_logs")
        )
        assert rows == [(Decimal("380.0"), Decimal("13.0"), None, Decimal("7.0"))]
    finally:
        command.upgrade(config, "head")


async def _execute(url: str, *statements: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for statement in statements:
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def _fetch(url: str, query: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return [tuple(row) for row in (await conn.execute(text(query))).all()]
    finally:
        await engine.dispose()
