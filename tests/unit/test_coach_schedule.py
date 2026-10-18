"""P6.11: schedule of program days, reminder stages, quiet hours, soft mode (ADR 0030)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_settings
from trainsync.coach.mode import CoachMode, MemorySoftModeStore, savage_configured
from trainsync.coach.schedule import (
    GRACE,
    PlannedDay,
    Stage,
    due_stage,
    is_quiet,
    scheduled_today,
    start_moment,
    weekday_of,
)

IST = ZoneInfo("Europe/Istanbul")


def day(index: int, weekday: int | None = None, start: time | None = None) -> PlannedDay:
    return PlannedDay(
        day_id=10 + index, day_index=index, name=f"Day {index}", weekday=weekday, start_time=start
    )


def test_default_spread_and_explicit_weekdays() -> None:
    days = [day(0), day(1), day(2), day(3)]
    assert [weekday_of(d, 4) for d in days] == [0, 1, 3, 4]  # Mon, Tue, Thu, Fri
    assert weekday_of(day(0, weekday=5), 4) == 5
    monday, wednesday = date(2026, 10, 19), date(2026, 10, 21)
    assert scheduled_today(days, 4, monday) == days[0]
    assert scheduled_today(days, 4, wednesday) is None
    assert scheduled_today([day(0), day(1), day(2)], 3, wednesday) == day(1)


def test_start_moment_uses_the_day_time_or_the_default() -> None:
    monday = date(2026, 10, 19)
    assert start_moment(monday, day(0), time(18, 0), IST) == datetime(
        2026, 10, 19, 15, 0, tzinfo=UTC
    )
    early = day(0, start=time(7, 30))
    assert start_moment(monday, early, time(18, 0), IST) == datetime(
        2026, 10, 19, 4, 30, tzinfo=UTC
    )


START = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(minutes=-45), None),
        (timedelta(minutes=-30), Stage.BEFORE),
        (timedelta(minutes=-16), Stage.BEFORE),
        (timedelta(minutes=-15), None),  # past the grace: never late
        (timedelta(0), Stage.NOW),
        (timedelta(minutes=31), Stage.NUDGE_30),
        (timedelta(minutes=95), Stage.NUDGE_90),
        (timedelta(minutes=180), Stage.MISSED),
        (timedelta(minutes=200), None),
    ],
)
def test_due_stage(offset: timedelta, expected: Stage | None) -> None:
    assert due_stage(START + offset, START, set()) == expected


def test_a_sent_stage_is_not_due_again() -> None:
    assert due_stage(START + timedelta(minutes=5), START, {Stage.NOW}) is None
    assert timedelta(minutes=15) == GRACE


@pytest.mark.parametrize(
    ("local", "quiet"),
    [
        (time(22, 59), False),
        (time(23, 0), True),
        (time(3, 0), True),
        (time(6, 59), True),
        (time(7, 0), False),
    ],
)
def test_quiet_hours_wrap_midnight(local: time, quiet: bool) -> None:
    moment = datetime.combine(date(2026, 10, 19), local, tzinfo=IST)
    assert is_quiet(moment, (time(23, 0), time(7, 0)), IST) is quiet


def test_quiet_window_inside_a_day_and_off() -> None:
    noon = datetime(2026, 10, 19, 12, 0, tzinfo=IST)
    assert is_quiet(noon, (time(12, 0), time(14, 0)), IST)
    assert not is_quiet(noon, (time(0, 0), time(0, 0)), IST)


def test_quiet_hours_setting() -> None:
    assert make_settings().quiet_window == (time(23, 0), time(7, 0))
    assert make_settings(quiet_hours="22:30-06:15").quiet_window == (time(22, 30), time(6, 15))
    with pytest.raises(ValueError, match="QUIET_HOURS"):
        make_settings(quiet_hours="late")


def test_savage_needs_hardcore_in_either_language() -> None:
    assert not savage_configured(make_settings())
    assert not savage_configured(make_settings(bot_intensity="savage"))
    for lang in ("en", "tr"):
        assert savage_configured(
            make_settings(bot_intensity="savage", bot_tone="hardcore", bot_lang=lang)
        )


async def test_soft_mode_turns_savage_off_until_hardened() -> None:
    soft = MemorySoftModeStore()
    mode = CoachMode(configured=True, soft=soft)
    assert await mode.savage()
    await soft.soften()
    assert not await mode.savage()
    await soft.harden()
    assert await mode.savage()
    assert not await CoachMode(configured=False, soft=MemorySoftModeStore()).savage()
