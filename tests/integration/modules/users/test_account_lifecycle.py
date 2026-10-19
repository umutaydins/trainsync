"""P8.6, ADR 0037: the data export and account deletion (soft delete now, purge in the worker)."""

from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import API_KEY, PASSWORD, Account, client, create_user, signed_in
from tests.support.factories import create_athlete, strava_activity
from tests.support.linked import link_chat
from trainsync.core.jobs import ArqJobQueue
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app
from trainsync.modules.activities.repository import ActivityRepository
from trainsync.modules.users.export import SECRET_COLUMNS, owned_tables
from trainsync.modules.users.lifecycle import purge


class Strava:
    def __init__(self) -> None:
        self.deauthorized: list[int] = []

    async def deauthorize(self, athlete_id: int) -> None:
        self.deauthorized.append(athlete_id)


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    async with LifespanManager(app):
        yield app


async def _rows_of(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> dict[str, int]:
    counts = {}
    async with sessionmaker() as session:
        for table in owned_tables():
            n = await session.scalar(
                select(func.count()).select_from(table).where(table.c.user_id == user_id)
            )
            if n:
                counts[table.name] = int(n)
    return counts


async def _seed(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession], account: Account
) -> None:
    user_id, email = account.id, account.email
    async with signed_in(app, account) as api:
        await api.put("/v1/checkins/2026-10-18", json={"status": "rest"})
        await api.post("/v1/nutrition/foods", json={"name": f"{email} bar", "kcal_100g": 400})
        await api.patch("/v1/me/settings", json={"lang": "tr"})
    athlete = await create_athlete(sessionmaker, 4000 + user_id, user_id=user_id)
    async with sessionmaker.begin() as session:
        await ActivityRepository(session).upsert_many(athlete, [strava_activity(9000 + user_id)])
    await link_chat(sessionmaker, 8000 + user_id, user_id)


async def test_export_has_every_row_of_mine_and_no_secret(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    await _seed(app, sessionmaker, alice)
    await _seed(app, sessionmaker, bob)
    async with signed_in(app, alice) as api:
        response = await api.get("/v1/me/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    document = response.json()
    assert document["account"]["email"] == alice.email
    assert "password_hash" not in document["account"]
    exported = {name: len(rows) for name, rows in document["tables"].items() if rows}
    assert exported == await _rows_of(sessionmaker, alice.id)
    assert {"activities", "daily_checkins", "foods", "user_settings", "telegram_chats"} <= set(
        exported
    )
    for rows in document["tables"].values():
        for row in rows:
            assert row["user_id"] == alice.id
            assert not SECRET_COLUMNS & set(row)
    assert "oauth_tokens" not in document["tables"]


async def test_delete_ends_access_at_once_and_the_purge_removes_everything(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    alice = await create_user(sessionmaker, "alice@example.com")
    bob = await create_user(sessionmaker, "bob@example.com")
    await _seed(app, sessionmaker, alice)
    await _seed(app, sessionmaker, bob)
    bob_rows = await _rows_of(sessionmaker, bob.id)
    async with signed_in(app, alice) as api:
        assert (
            await api.request("DELETE", "/v1/me", json={"password": "wrong!"})
        ).status_code == 401
        deleted = await api.request("DELETE", "/v1/me", json={"password": PASSWORD})
        assert deleted.status_code == 204
        assert (await api.get("/v1/me")).status_code == 401  # the session ended with it
    queue: ArqJobQueue = app.state.job_queue
    jobs = [(j.function, j.args) for j in await queue.pool.queued_jobs()]
    assert ("purge_user", (alice.id,)) in jobs
    assert "telegram_chats" not in await _rows_of(sessionmaker, alice.id)  # unlinked at once

    strava = Strava()
    assert await purge(sessionmaker, strava, alice.id) == "purged"
    assert strava.deauthorized  # Strava was told while the tokens still existed
    assert await _rows_of(sessionmaker, alice.id) == {}
    assert await _rows_of(sessionmaker, bob.id) == bob_rows  # nobody else lost anything
    assert await purge(sessionmaker, strava, bob.id) == "not_deleted"
    # The email is free again.
    async with client(app, **{"X-API-Key": API_KEY}) as owner:
        code = (await owner.post("/v1/admin/invites", json={})).json()["code"]
    async with client(app) as anonymous:
        again = await anonymous.post(
            "/v1/auth/register",
            json={"email": alice.email, "password": PASSWORD, "invite_code": code},
        )
    assert again.status_code == 201


async def test_the_owner_account_cannot_be_deleted(app: FastAPI) -> None:
    async with client(app, **{"X-API-Key": API_KEY}) as owner:
        response = await owner.request("DELETE", "/v1/me", json={"password": PASSWORD})
    assert response.status_code == 403
