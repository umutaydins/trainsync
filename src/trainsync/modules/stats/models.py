"""The per-user data version behind the statistics cache (ADR 0038).

A row trigger on every table in `VERSIONED_TABLES` bumps the user's version on each insert,
update and delete (migration 0018), so a cached result keyed by the version is never read again
once the user's data changed, whoever changed it.
"""

from sqlalchemy import BigInteger, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base

# The tables the statistics read. A new one needs the trigger in its migration
# (tests/integration/modules/stats/test_stats_cache.py checks the database against this list).
VERSIONED_TABLES = (
    "activities",
    "workouts",
    "workout_sets",
    "exercises",
    "programs",
    "program_days",
    "program_exercises",
    "food_logs",
    "nutrition_profile",
    "body_metrics",
    "daily_checkins",
)


class UserDataVersion(Base):
    __tablename__ = "user_data_versions"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
