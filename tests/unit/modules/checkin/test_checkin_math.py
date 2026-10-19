"""P6.9: streaks and adherence against the hand-computed fixture, and the scheduler's decision
(injected clock, DST-safe local wall time)."""

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from trainsync.core.localtime import local_moment, local_today
from trainsync.modules.checkin.models import CheckinStatus
from trainsync.modules.checkin.streaks import adherence, current_streak, longest_streak
from trainsync.modules.notifications.checkin import Decision, day_key, decide

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parents[3] / "fixtures" / "checkins.json").read_text(encoding="utf-8")
)
STATUSES = {date.fromisoformat(d): CheckinStatus(s) for d, s in FIXTURE["days"].items()}
TODAY = date.fromisoformat(FIXTURE["today"])
CASES = FIXTURE["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_adherence_matches_the_fixture(case: dict[str, Any]) -> None:
    start, end = date.fromisoformat(case["from"]), date.fromisoformat(case["to"])
    result = adherence(STATUSES, start, end, FIXTURE["days_per_week"])
    assert (result.planned, result.done) == (case["planned"], case["done"])
    assert result.ratio == pytest.approx(case["adherence"])
    assert [[w.week_start.isoformat(), w.planned, w.done] for w in result.weeks] == case["weeks"]


def test_streaks_match_the_fixture() -> None:
    assert current_streak(STATUSES, TODAY) == CASES[0]["current_streak"]
    assert longest_streak(STATUSES, TODAY) == CASES[0]["longest_streak"]


def test_streak_rules() -> None:
    day = date(2026, 10, 18)
    # Today's check-in counts as soon as it exists; a skip today ends the streak.
    assert current_streak({**STATUSES, day: CheckinStatus.DONE}, day) == 14
    assert current_streak({**STATUSES, day: CheckinStatus.SKIPPED}, day) == 0
    # A missing yesterday: nothing to count back from.
    assert current_streak(STATUSES, day + timedelta(days=2)) == 0
    assert current_streak({}, day) == 0
    assert longest_streak({}, day) == 0
    # Only days up to `until` count.
    assert longest_streak(STATUSES, date(2026, 9, 20)) == 11


def test_no_program_means_unknown_adherence() -> None:
    result = adherence(STATUSES, date(2026, 9, 28), TODAY, None)
    assert (result.planned, result.done, result.ratio) == (0, 0, None)
    assert len(result.weeks) == 3


# ---------------------------------------------------------------- scheduler decision

ISTANBUL = ZoneInfo("Europe/Istanbul")
BERLIN = ZoneInfo("Europe/Berlin")
NINE_PM = time(21, 0)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


def run(now: datetime, zone: ZoneInfo = ISTANBUL, **facts: Any) -> Decision:
    values: dict[str, Any] = {"has_checkin": False, "prompt_sent_at": None, "reminder_sent": False}
    values.update(facts)
    return decide(now, zone, NINE_PM, 90, **values)


def test_prompt_at_the_local_time_only() -> None:
    assert run(utc(2026, 10, 18, 17, 55)) == Decision.NOTHING  # 20:55 in Istanbul
    assert run(utc(2026, 10, 18, 18, 0)) == Decision.PROMPT  # 21:00
    assert run(utc(2026, 10, 18, 20, 59)) == Decision.PROMPT  # still today, not sent yet
    # 21:30 UTC is already the next local day (00:30), before its 21:00.
    assert run(utc(2026, 10, 18, 21, 30)) == Decision.NOTHING


def test_no_prompt_when_todays_check_in_exists() -> None:
    assert run(utc(2026, 10, 18, 18, 0), has_checkin=True) == Decision.NOTHING
    assert run(
        utc(2026, 10, 18, 20, 0), has_checkin=True, prompt_sent_at=utc(2026, 10, 18, 18, 0)
    ) == (Decision.NOTHING)


def test_one_reminder_after_the_configured_minutes() -> None:
    sent = utc(2026, 10, 18, 18, 0)
    assert run(utc(2026, 10, 18, 19, 25), prompt_sent_at=sent) == Decision.NOTHING
    assert run(utc(2026, 10, 18, 19, 30), prompt_sent_at=sent) == Decision.REMINDER
    assert run(utc(2026, 10, 18, 20, 30), prompt_sent_at=sent, reminder_sent=True) == (
        Decision.NOTHING
    )
    no_reminders = decide(
        utc(2026, 10, 18, 20, 30),
        ISTANBUL,
        NINE_PM,
        0,
        has_checkin=False,
        prompt_sent_at=sent,
        reminder_sent=False,
    )
    assert no_reminders == Decision.NOTHING


@pytest.mark.parametrize(
    ("day", "due_utc"),
    [
        (date(2026, 3, 28), utc(2026, 3, 28, 20, 0)),  # CET, UTC+1
        (date(2026, 3, 29), utc(2026, 3, 29, 19, 0)),  # spring forward that night: CEST, UTC+2
        (date(2026, 10, 25), utc(2026, 10, 25, 20, 0)),  # fall back that morning: CET again
    ],
)
def test_local_time_is_dst_safe(day: date, due_utc: datetime) -> None:
    """21:00 stays 21:00 on the wall clock across DST changes, once per local date."""
    assert local_moment(day, NINE_PM, BERLIN) == due_utc
    before = due_utc - timedelta(minutes=5)
    assert run(before, BERLIN) == Decision.NOTHING
    assert run(due_utc, BERLIN) == Decision.PROMPT
    assert run(due_utc + timedelta(minutes=30), BERLIN, prompt_sent_at=due_utc) == Decision.NOTHING


def test_wall_times_inside_a_dst_gap_or_overlap() -> None:
    # 02:30 does not exist on 29 Mar in Berlin: the instant after the gap (03:30 CEST).
    assert local_moment(date(2026, 3, 29), time(2, 30), BERLIN) == utc(2026, 3, 29, 1, 30)
    # 02:30 happens twice on 25 Oct: the first one (CEST).
    # (Compared in UTC: ambiguous local times never equal another zone's, PEP 495.)
    overlap = local_moment(date(2026, 10, 25), time(2, 30), BERLIN)
    assert overlap.astimezone(UTC) == utc(2026, 10, 25, 0, 30)


def test_local_today_and_day_key() -> None:
    assert local_today(lambda: utc(2026, 10, 18, 21, 30), ISTANBUL) == date(2026, 10, 19)
    assert day_key(date(2026, 10, 8)) == 20261008
