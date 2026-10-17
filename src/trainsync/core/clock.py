"""Injectable time sources, so time-dependent code is deterministic in tests."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


def utc_now() -> datetime:
    return datetime.now(UTC)


async def real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)
