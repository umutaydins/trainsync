"""Numbers as chat text: distance, duration, elevation, pace or speed, and a sport's emoji.
Metric units throughout; the unit symbols are the same in every language."""

METERS_PER_KM = 1000
SWIM_PACE_METERS = 100  # swim pace is per 100 m
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600

_EMOJI = {
    "Run": "🏃",
    "TrailRun": "🏃",
    "VirtualRun": "🏃",
    "Walk": "🚶",
    "Hike": "🥾",
    "Ride": "🚴",
    "GravelRide": "🚴",
    "MountainBikeRide": "🚵",
    "VirtualRide": "🚴",
    "EBikeRide": "🚴",
    "Swim": "🏊",
    "Rowing": "🚣",
    "WeightTraining": "🏋️",
    "Workout": "💪",
    "Yoga": "🧘",
    "AlpineSki": "⛷️",
    "NordicSki": "⛷️",
}
_PACE_SPORTS = {"Run", "TrailRun", "VirtualRun", "Walk", "Hike"}
_SWIM_SPORTS = {"Swim"}


def sport_emoji(sport_type: str) -> str:
    return _EMOJI.get(sport_type, "🏅")


def km(distance_m: float) -> str:
    return f"{distance_m / METERS_PER_KM:.1f} km"


def duration(seconds: int) -> str:
    """`1h 05m` from one hour on, else `42m 10s`."""
    hours, rest = divmod(max(seconds, 0), SECONDS_PER_HOUR)
    minutes, secs = divmod(rest, SECONDS_PER_MINUTE)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def elevation(meters: float) -> str:
    return f"↑ {meters:.0f} m"


def pace_or_speed(sport_type: str, distance_m: float, moving_time_s: int) -> str | None:
    """min/km for foot sports, min/100 m for swims, km/h otherwise; None without distance."""
    if distance_m <= 0 or moving_time_s <= 0:
        return None
    if sport_type in _PACE_SPORTS:
        return f"{_min_sec(moving_time_s / (distance_m / METERS_PER_KM))} /km"
    if sport_type in _SWIM_SPORTS:
        return f"{_min_sec(moving_time_s / (distance_m / SWIM_PACE_METERS))} /100 m"
    return f"{distance_m / METERS_PER_KM / (moving_time_s / SECONDS_PER_HOUR):.1f} km/h"


def _min_sec(seconds: float) -> str:
    total = round(seconds)
    return f"{total // SECONDS_PER_MINUTE}:{total % SECONDS_PER_MINUTE:02d}"
