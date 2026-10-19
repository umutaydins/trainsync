from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from trainsync.integrations.strava.errors import StravaAuthError
from trainsync.integrations.strava.models import TokenResponse
from trainsync.modules.strava.token_repository import Tokens
from trainsync.modules.strava.tokens import TokenManager, TokenRefreshTimeoutError

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@dataclass
class MemoryStore:
    tokens: dict[int, Tokens] = field(default_factory=dict)

    async def get(self, athlete_id: int) -> Tokens | None:
        return self.tokens.get(athlete_id)

    async def save(self, athlete_id: int, tokens: Tokens) -> None:
        self.tokens[athlete_id] = tokens


@dataclass
class MemoryLock:
    holders: dict[int, str] = field(default_factory=dict)
    releases: list[tuple[int, str]] = field(default_factory=list)

    async def acquire(self, athlete_id: int) -> str | None:
        if athlete_id in self.holders:
            return None
        self.holders[athlete_id] = f"owner-{len(self.releases)}"
        return self.holders[athlete_id]

    async def release(self, athlete_id: int, owner: str) -> None:
        self.releases.append((athlete_id, owner))
        if self.holders.get(athlete_id) == owner:
            del self.holders[athlete_id]

    async def is_held(self, athlete_id: int) -> bool:
        return athlete_id in self.holders


@dataclass
class Refresher:
    calls: list[str] = field(default_factory=list)
    fail: Exception | None = None

    async def refresh(self, refresh_token: str) -> TokenResponse:
        self.calls.append(refresh_token)
        if self.fail is not None:
            raise self.fail
        n = len(self.calls)
        return TokenResponse(
            access_token=f"access-{n + 1}",
            refresh_token=f"refresh-{n + 1}",
            expires_at=NOW + timedelta(hours=6),
        )


def tokens(expires_in: timedelta, n: int = 1) -> Tokens:
    return Tokens(f"access-{n}", f"refresh-{n}", NOW + expires_in, "read,activity:read_all")


def manager(
    store: MemoryStore, lock: MemoryLock, refresher: Refresher, now: datetime = NOW
) -> TokenManager:
    async def no_sleep(_: float) -> None:
        return None

    return TokenManager(store, lock, refresher, clock=lambda: now, sleep=no_sleep)


async def test_valid_token_is_not_refreshed() -> None:
    store, refresher = MemoryStore({1: tokens(timedelta(minutes=6))}), Refresher()
    assert await manager(store, MemoryLock(), refresher).access_token(1) == "access-1"
    assert refresher.calls == []


async def test_expiring_token_is_refreshed_exactly_once() -> None:
    store, refresher = MemoryStore({1: tokens(timedelta(minutes=4))}), Refresher()
    tm = manager(store, MemoryLock(), refresher)
    assert await tm.access_token(1) == "access-2"
    assert await tm.access_token(1) == "access-2"
    assert refresher.calls == ["refresh-1"]


async def test_rotated_refresh_token_is_persisted_and_used_next_time() -> None:
    store, refresher = MemoryStore({1: tokens(timedelta(0))}), Refresher()
    await manager(store, MemoryLock(), refresher).access_token(1)
    assert store.tokens[1].refresh_token == "refresh-2"
    assert store.tokens[1].scope == "read,activity:read_all"
    later = NOW + timedelta(hours=6)
    await manager(store, MemoryLock(), refresher, now=later).access_token(1)
    assert refresher.calls == ["refresh-1", "refresh-2"]  # the old one is never reused


async def test_force_refresh_skips_when_token_already_replaced() -> None:
    store, refresher = MemoryStore({1: tokens(timedelta(hours=1))}), Refresher()
    tm = manager(store, MemoryLock(), refresher)
    assert await tm.force_refresh(1) == "access-2"
    assert refresher.calls == ["refresh-1"]


async def test_lock_released_when_refresh_fails() -> None:
    store, lock = MemoryStore({1: tokens(timedelta(0))}), MemoryLock()
    refresher = Refresher(fail=StravaAuthError("revoked"))
    with pytest.raises(StravaAuthError):
        await manager(store, lock, refresher).access_token(1)
    assert lock.holders == {}
    assert len(lock.releases) == 1


async def test_waiter_uses_token_refreshed_by_holder() -> None:
    store, lock, refresher = MemoryStore({1: tokens(timedelta(0))}), MemoryLock(), Refresher()
    lock.holders[1] = "someone-else"

    async def holder_finishes(_: float) -> None:
        store.tokens[1] = tokens(timedelta(hours=6), n=9)
        del lock.holders[1]

    tm = TokenManager(store, lock, refresher, clock=lambda: NOW, sleep=holder_finishes)
    assert await tm.access_token(1) == "access-9"
    assert refresher.calls == []
    assert lock.releases == []  # never touched someone else's lock


async def test_waiting_is_bounded() -> None:
    store, lock = MemoryStore({1: tokens(timedelta(0))}), MemoryLock()
    lock.holders[1] = "stuck"
    with pytest.raises(TokenRefreshTimeoutError):
        await manager(store, lock, Refresher()).access_token(1)
    assert lock.holders == {1: "stuck"}


async def test_missing_tokens_is_auth_error() -> None:
    with pytest.raises(StravaAuthError):
        await manager(MemoryStore(), MemoryLock(), Refresher()).access_token(1)
