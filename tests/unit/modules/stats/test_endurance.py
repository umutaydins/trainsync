from datetime import UTC, datetime

import pytest

from trainsync.modules.stats.endurance import Effort, GroupTotals, SportGroup


def totals(group: SportGroup, distance_m: float, moving_time_s: int) -> GroupTotals:
    return GroupTotals(group, 1, distance_m, moving_time_s, 0.0, 0, 0.0)


@pytest.mark.parametrize(
    ("group", "distance_m", "moving_time_s", "speed_mps"),
    [
        # 1500 m in 30:00 is 2:00 /100 m
        (SportGroup.SWIM, 1500.0, 1800, 1500 / 1800),
        # 10 km in 50:00 is 5:00 /km
        (SportGroup.RUN, 10_000.0, 3000, 10_000 / 3000),
        # 5 km in 1:00:00 is 12:00 /km
        (SportGroup.WALK, 5000.0, 3600, 5000 / 3600),
        # 30 km in 1:00:00 is 30 km/h
        (SportGroup.RIDE, 30_000.0, 3600, 30_000 / 3600),
    ],
)
def test_average_speed_is_metres_per_second(
    group: SportGroup, distance_m: float, moving_time_s: int, speed_mps: float
) -> None:
    assert totals(group, distance_m, moving_time_s).average_speed_mps == pytest.approx(speed_mps)
    effort = Effort(group, 1, "x", datetime(2026, 10, 1, tzinfo=UTC), distance_m, moving_time_s)
    assert effort.average_speed_mps == pytest.approx(speed_mps)


def test_swim_pace_from_the_average_speed() -> None:
    speed = totals(SportGroup.SWIM, 1500.0, 1800).average_speed_mps
    assert speed is not None
    assert 100 / speed == pytest.approx(120.0)  # seconds per 100 m


def test_no_moving_time_has_no_speed() -> None:
    assert totals(SportGroup.SWIM, 1500.0, 0).average_speed_mps is None
