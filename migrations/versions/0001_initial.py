"""initial schema: athletes, oauth_tokens, activities, sync_runs, webhook_events

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _utc(name: str, *, nullable: bool = False, default_now: bool = False) -> sa.Column[object]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default_now else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "athletes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("strava_athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _utc("created_at", default_now=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_athletes")),
        sa.UniqueConstraint("strava_athlete_id", name=op.f("uq_athletes_strava_athlete_id")),
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=False),
        _utc("expires_at"),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name=op.f("fk_oauth_tokens_athlete_id_athletes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("athlete_id", name=op.f("pk_oauth_tokens")),
    )
    op.create_table(
        "activities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("strava_activity_id", sa.BigInteger(), nullable=False),
        sa.Column("athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sport_type", sa.String(length=64), nullable=False),
        _utc("start_date"),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("moving_time_s", sa.Integer(), nullable=False),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=False),
        sa.Column("elevation_gain_m", sa.Float(), nullable=False),
        sa.Column("average_heartrate", sa.Float(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _utc("deleted_at", nullable=True),
        _utc("synced_at", default_now=True),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name=op.f("fk_activities_athlete_id_athletes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
        sa.UniqueConstraint("strava_activity_id", name=op.f("uq_activities_strava_activity_id")),
    )
    op.create_index(
        "ix_activities_athlete_start_date",
        "activities",
        ["athlete_id", sa.literal_column("start_date DESC")],
    )
    op.create_index(
        "ix_activities_athlete_sport_start_date",
        "activities",
        ["athlete_id", "sport_type", "start_date"],
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "cursor",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("pages", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("upserted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        _utc("started_at", default_now=True),
        _utc("finished_at", nullable=True),
        sa.CheckConstraint("kind IN ('backfill', 'incremental')", name=op.f("ck_sync_runs_kind")),
        sa.CheckConstraint(
            "status IN ('running', 'paused', 'succeeded', 'failed')",
            name=op.f("ck_sync_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name=op.f("fk_sync_runs_athlete_id_athletes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _utc("received_at", default_now=True),
        _utc("processed_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'processed', 'failed')",
            name=op.f("ck_webhook_events_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_webhook_events_dedup_key")),
    )
    op.create_index(
        "ix_webhook_events_status_received_at", "webhook_events", ["status", "received_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_events_status_received_at", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_table("sync_runs")
    op.drop_index("ix_activities_athlete_sport_start_date", table_name="activities")
    op.drop_index("ix_activities_athlete_start_date", table_name="activities")
    op.drop_table("activities")
    op.drop_table("oauth_tokens")
    op.drop_table("athletes")
