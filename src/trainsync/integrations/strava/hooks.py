"""What the Strava client needs from its collaborators: tokens per athlete and the shared rate
budget (implemented in `modules/strava` and `budget.py`)."""

from datetime import datetime
from typing import Protocol

from trainsync.integrations.strava.budget import Allowance, Priority
from trainsync.integrations.strava.ratelimit import RateLimitSnapshot


class TokenProvider(Protocol):
    async def access_token(self, athlete_id: int) -> str: ...

    async def force_refresh(self, athlete_id: int) -> str: ...


class RateLimitHook(Protocol):
    """What the client needs from the rate budget (implemented by `RateBudget`)."""

    async def allow(self, priority: Priority) -> Allowance: ...

    async def record(self, snapshot: RateLimitSnapshot) -> None: ...

    async def block_until(self, reset_at: datetime) -> None: ...
