"""Sent notifications (claimed before sending, ADR 0012)."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, check_in, owner_id, utc_timestamp


class NotificationKind(StrEnum):
    NEW_ACTIVITY = "new_activity"
    # Daily check-in (P6.9, ADR 0020); object_id is the local date as yyyymmdd.
    CHECKIN_PROMPT = "checkin_prompt"
    CHECKIN_REMINDER = "checkin_reminder"
    # Coach (P6.11, ADR 0030). Reminder stages: object_id = local date (yyyymmdd); workout
    # messages: the workout id; rest over: the set id; under target: workout id * 100000 +
    # exercise id (once per exercise per workout).
    COACH_REMINDER_BEFORE = "coach_reminder_before"
    COACH_REMINDER_NOW = "coach_reminder_now"
    COACH_NUDGE_30 = "coach_nudge_30"
    COACH_NUDGE_90 = "coach_nudge_90"
    COACH_MISSED = "coach_missed"
    COACH_WORKOUT_START = "coach_workout_start"
    COACH_REST_OVER = "coach_rest_over"
    COACH_UNDER_TARGET = "coach_under_target"
    COACH_WORKOUT_DONE = "coach_workout_done"


class Notification(Base):
    """One row per notification ever sent: the unique `(user_id, kind, object_id)` makes sending
    idempotent (claimed before sending, released if the send fails; ADR 0012, 0035)."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(check_in("kind", NotificationKind), name="kind"),
        UniqueConstraint(
            "user_id", "kind", "object_id", name="uq_notifications_user_kind_object_id"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = owner_id()
    kind: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[int] = mapped_column(BigInteger)
    sent_at: Mapped[datetime] = utc_timestamp(default_now=True)
