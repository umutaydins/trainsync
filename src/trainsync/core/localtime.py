"""The owner's local day and wall-clock time (`CHECKIN_TZ`, ADR 0020).

The read API reports UTC days; the bot and the check-in scheduler speak in the owner's local
days, because "today" at 01:00 in Istanbul is still yesterday in UTC.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from trainsync.core.clock import Clock


def local_now(clock: Clock, zone: ZoneInfo) -> datetime:
    return clock().astimezone(zone)


def local_today(clock: Clock, zone: ZoneInfo) -> date:
    return local_now(clock, zone).date()


def local_moment(day: date, wall: time, zone: ZoneInfo) -> datetime:
    """The instant the wall clock in `zone` shows `wall` on `day`.

    DST-safe: a wall time that falls into a spring-forward gap maps to the instant after the gap
    (02:30 on a 02:00→03:00 day is 03:30), an ambiguous one in the autumn to its first occurrence.
    """
    naive = datetime.combine(day, wall)
    first = naive.replace(tzinfo=zone, fold=0)
    # In a gap, fold=0 uses the offset before the change: round-tripping through UTC lands on
    # the real instant after the gap.
    return first.astimezone(ZoneInfo("UTC")).astimezone(zone)
