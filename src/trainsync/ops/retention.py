"""Backup retention: which backups to keep (ADR 0024). Pure functions, no I/O.

A backup is named `trainsync-YYYYMMDD-HHMMSS[-label].dump.age`, timestamp in UTC. The rules
count *buckets that have a backup*, not calendar windows, so a two-week gap (the Mac was off)
does not wipe out everything older than the gap:

- daily: the newest backup of each of the 7 most recent UTC days that have one;
- weekly: the newest of each of the 4 most recent ISO weeks that have one;
- monthly: the newest of each of the 6 most recent months that have one;
- the newest backup overall is always kept.

A backup kept by one rule still counts for the others (a Sunday backup can be both the daily
and the weekly one). Names that do not parse are left alone (never deleted). Backups dated
after `now` (clock skew, a restored file) are kept and take no bucket.
"""

import re
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

LABEL_RE = re.compile(r"[a-z0-9]+")
NAME_RE = re.compile(
    r"^trainsync-(?P<ts>\d{8}-\d{6})(?:-(?P<label>[a-z0-9]+))?\.dump\.age$",
)
SUFFIX = ".dump.age"
COUNTS_SUFFIX = ".counts.json"


@dataclass(frozen=True)
class Policy:
    daily: int = 7
    weekly: int = 4
    monthly: int = 6


DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Backup:
    name: str
    taken_at: datetime


@dataclass(frozen=True)
class Plan:
    keep: tuple[str, ...]
    delete: tuple[str, ...]
    ignored: tuple[str, ...]


def backup_name(taken_at: datetime, label: str | None = None) -> str:
    stamp = taken_at.astimezone(UTC).strftime("%Y%m%d-%H%M%S")
    return f"trainsync-{stamp}{f'-{label}' if label else ''}{SUFFIX}"


def parse_name(name: str) -> Backup | None:
    match = NAME_RE.match(name)
    if match is None:
        return None
    try:
        taken_at = datetime.strptime(match["ts"], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:  # e.g. month 13: shaped right, not a date
        return None
    return Backup(name=name, taken_at=taken_at)


def counts_name(backup: str) -> str:
    """The sidecar with the row counts recorded at backup time."""
    return backup.removesuffix(SUFFIX) + COUNTS_SUFFIX


def _newest_per_bucket(
    backups: list[Backup], key: Callable[[datetime], Hashable], count: int
) -> set[str]:
    """`backups` sorted newest first: the first backup seen in each bucket is its newest."""
    kept: dict[Hashable, str] = {}
    for backup in backups:
        bucket = key(backup.taken_at)
        if bucket not in kept:
            if len(kept) == count:
                break
            kept[bucket] = backup.name
    return set(kept.values())


def plan(names: Iterable[str], now: datetime, policy: Policy = DEFAULT_POLICY) -> Plan:
    parsed: list[Backup] = []
    ignored: list[str] = []
    future: list[str] = []
    for name in names:
        backup = parse_name(name)
        if backup is None:
            ignored.append(name)
        elif backup.taken_at > now:
            future.append(name)
        else:
            parsed.append(backup)
    parsed.sort(key=lambda b: (b.taken_at, b.name), reverse=True)

    keep = set(future)
    if parsed:
        keep.add(parsed[0].name)
    keep |= _newest_per_bucket(parsed, lambda t: t.date(), policy.daily)
    keep |= _newest_per_bucket(parsed, lambda t: t.isocalendar()[:2], policy.weekly)
    keep |= _newest_per_bucket(parsed, lambda t: (t.year, t.month), policy.monthly)
    delete = [b.name for b in parsed if b.name not in keep]
    return Plan(keep=tuple(sorted(keep)), delete=tuple(sorted(delete)), ignored=tuple(ignored))
