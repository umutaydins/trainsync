"""Accounts for tests: the owner every API-key request acts as (inserted by `clean_state`),
users created straight in the database, and signed-in API clients."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.security import hash_password
from trainsync.modules.auth.models import UserRole
from trainsync.modules.auth.repository import UserRepository

OWNER_EMAIL = "owner@example.com"
OWNER_ID = 1
PASSWORD = "correct horse battery"
API_KEY = "test-api-key"
BASE_URL = "http://api"


@dataclass(frozen=True, slots=True)
class Account:
    id: int
    email: str
    password: str = PASSWORD


async def create_user(
    sessionmaker: async_sessionmaker[AsyncSession],
    email: str,
    *,
    password: str = PASSWORD,
    timezone: str = "UTC",
    role: UserRole = UserRole.USER,
) -> Account:
    hashed = await hash_password(password)
    async with sessionmaker.begin() as session:
        user = await UserRepository(session).add(
            email=email, password_hash=hashed, display_name=email, timezone=timezone, role=role
        )
    return Account(user.id, email, password)


def client(app: FastAPI, **headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE_URL, headers=headers
    )


async def login(app: FastAPI, account: Account) -> dict[str, Any]:
    async with client(app) as anonymous:
        response = await anonymous.post(
            "/v1/auth/login", json={"email": account.email, "password": account.password}
        )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


@asynccontextmanager
async def signed_in(app: FastAPI, account: Account) -> AsyncIterator[httpx.AsyncClient]:
    token = (await login(app, account))["token"]
    async with client(app, Authorization=f"Bearer {token}") as api:
        yield api
