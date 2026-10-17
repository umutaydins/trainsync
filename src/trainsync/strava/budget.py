"""Rate-limit budget: may a call of a given priority go to Strava now?"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

# `high`: webhook-driven fetches (fresh data the athlete just produced). `low`: backfill and
# incremental sync, which can always wait for the next window.
Priority = Literal["high", "low"]


@dataclass(frozen=True, slots=True)
class Allowance:
    allowed: bool
    resume_at: datetime | None = None


class Budget(Protocol):
    async def allow(self, priority: Priority) -> Allowance: ...


class UnlimitedBudget:
    async def allow(self, priority: Priority) -> Allowance:
        return Allowance(allowed=True)
