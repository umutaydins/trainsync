"""The data export (KVKK / GDPR, ADR 0037): every row the user owns, as JSON.

Driven by the metadata, so a new user-owned table is exported without touching this file:
every table with a `user_id` column, minus secrets (token and password hashes, encrypted
tokens) and the tables that only hold them.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.models import Base

SECRET_COLUMNS = frozenset(
    {"password_hash", "token_hash", "code_hash", "access_token_enc", "refresh_token_enc"}
)
SECRET_TABLES = frozenset({"oauth_tokens", "password_resets"})
EXPORT_VERSION = 1


def _json(value: object) -> object:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def owned_tables() -> list[Table]:
    return [
        table
        for table in Base.metadata.sorted_tables
        if "user_id" in table.c and table.name not in SECRET_TABLES
    ]


async def _rows(session: AsyncSession, table: Table, where: Any) -> list[dict[str, object]]:
    columns = [c for c in table.c if c.name not in SECRET_COLUMNS]
    result = await session.execute(select(*columns).where(where))
    return [{k: _json(v) for k, v in row._mapping.items()} for row in result]


async def export_user(session: AsyncSession, user_id: int, now: datetime) -> dict[str, object]:
    users = Base.metadata.tables["users"]
    account = await _rows(session, users, users.c.id == user_id)
    tables = {
        table.name: await _rows(session, table, table.c.user_id == user_id)
        for table in owned_tables()
    }
    return {
        "version": EXPORT_VERSION,
        "exported_at": now.isoformat(),
        "account": account[0] if account else None,
        "tables": tables,
    }
