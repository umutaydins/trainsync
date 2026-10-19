"""P8.1: `python -m trainsync.entrypoints.cli` — invites, the owner's password, reset links."""

import io

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_ENV
from tests.support.accounts import OWNER_EMAIL, create_user
from trainsync.core.security import verify_password
from trainsync.entrypoints.cli.__main__ import run
from trainsync.modules.auth.models import Invite, User, UserRole


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, pg_url: str, redis_url: str) -> None:
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("OWNER_EMAIL", OWNER_EMAIL)
    monkeypatch.setenv("DASHBOARD_PUBLIC_URL", "https://dash.example")


async def test_invite_create_list_revoke(
    capsys: pytest.CaptureFixture[str], sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    assert await run(["invite", "create", "--note", "Ayşe"]) == 0
    out = capsys.readouterr().out
    assert "link: https://dash.example/register?invite=" in out
    async with sessionmaker() as session:
        invite = await session.scalar(select(Invite))
    assert invite is not None
    assert await run(["invite", "list"]) == 0
    assert "open" in capsys.readouterr().out
    assert await run(["invite", "revoke", str(invite.id)]) == 0
    assert await run(["invite", "revoke", str(invite.id)]) == 1


async def test_owner_set_password_and_reset_link(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("the owner's new password\n"))
    assert await run(["owner", "set-password", "--stdin"]) == 0
    async with sessionmaker() as session:
        owner = await session.scalar(select(User).where(User.role == UserRole.OWNER.value))
    assert owner is not None
    assert await verify_password("the owner's new password", owner.password_hash)
    account = await create_user(sessionmaker, "a@example.com")
    capsys.readouterr()
    assert await run(["owner", "reset-link", account.email.upper()]) == 0
    assert "https://dash.example/reset-password?token=" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="no account"):
        await run(["owner", "reset-link", "nobody@example.com"])
