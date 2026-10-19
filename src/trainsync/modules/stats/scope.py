"""Whose statistics, in which zone (P8.10)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Date, cast, func


@dataclass(frozen=True, slots=True)
class Scope:
    user_id: int
    zone: ZoneInfo
    # Activities count only from the user's connected athletes (as everywhere in the read API).
    athlete_ids: Sequence[int]

    def local_date(self, instant: ColumnElement[datetime] | Any) -> ColumnElement[Any]:
        """The local calendar day of a `timestamptz` column, computed in Postgres."""
        return cast(func.timezone(self.zone.key, instant), Date)
