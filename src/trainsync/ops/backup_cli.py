"""The decisions the backup container's shell loop delegates to Python (ADR 0024).

    python3 -m trainsync.ops.backup_cli name [--label L]          # new backup file name (UTC)
    python3 -m trainsync.ops.backup_cli due --dir D --at 03:30 --tz Europe/Berlin
    python3 -m trainsync.ops.backup_cli latest --dir D
    python3 -m trainsync.ops.backup_cli prune --dir D [--dry-run]
    python3 -m trainsync.ops.backup_cli compare-counts EXPECTED.json ACTUAL.json

`due` exits 0 when today's slot has passed (local time in --tz) and no backup was taken since
it: a Mac that slept through 03:30 backs up on wake, and a restarted container does not take
a second one. Exit codes: 0 yes/ok, 1 no/mismatch, 2 usage error.
"""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from trainsync.ops.retention import (
    LABEL_RE,
    backup_name,
    counts_name,
    parse_name,
    plan,
)

# Tables whose absence from a restored dump fails the check even when the counts agree.
KEY_TABLES = (
    "athletes",
    "activities",
    "workouts",
    "workout_sets",
    "food_logs",
    "daily_checkins",
    "body_metrics",
)

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def is_due(now: datetime, at: time, tz: ZoneInfo, taken: Sequence[datetime]) -> bool:
    local_now = now.astimezone(tz)
    slot = datetime.combine(local_now.date(), at, tzinfo=tz)
    if local_now < slot:
        return False
    return not any(t >= slot for t in taken)


def compare_counts(
    expected: Mapping[str, int], actual: Mapping[str, int], required: Sequence[str] = KEY_TABLES
) -> list[str]:
    problems = [f"{t}: missing from the restored database" for t in required if t not in actual]
    for table in sorted(set(expected) | set(actual)):
        want, got = expected.get(table), actual.get(table)
        if want != got:
            problems.append(f"{table}: backup recorded {want}, restore has {got}")
    return problems


def _backups(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.is_file())


def _load_counts(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in data.items()
    ):
        raise ValueError(f"{path}: expected a JSON object of table -> row count")
    return data


def _parse_at(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a HH:MM time: {value!r}") from None


def _parse_label(value: str) -> str:
    if not LABEL_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"labels are lowercase letters and digits: {value!r}")
    return value


def _parse_tz(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise argparse.ArgumentTypeError(f"unknown time zone: {value!r}") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backup_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    name = sub.add_parser("name")
    name.add_argument("--label", type=_parse_label, default=None)
    due = sub.add_parser("due")
    due.add_argument("--dir", type=Path, required=True)
    due.add_argument("--at", type=_parse_at, required=True)
    due.add_argument("--tz", type=_parse_tz, required=True)
    latest = sub.add_parser("latest")
    latest.add_argument("--dir", type=Path, required=True)
    prune = sub.add_parser("prune")
    prune.add_argument("--dir", type=Path, required=True)
    prune.add_argument("--dry-run", action="store_true")
    compare = sub.add_parser("compare-counts")
    compare.add_argument("expected", type=Path)
    compare.add_argument("actual", type=Path)
    return parser


def _prune(directory: Path, now: datetime, dry_run: bool) -> int:
    result = plan(_backups(directory), now)
    for name in result.delete:
        print(f"prune: {'would delete' if dry_run else 'deleting'} {name}")
        if not dry_run:
            (directory / counts_name(name)).unlink(missing_ok=True)
            (directory / name).unlink(missing_ok=True)
    print(f"prune: keeping {len(result.keep)}, deleting {len(result.delete)}")
    return 0


def _compare(expected_path: Path, actual_path: Path) -> int:
    expected, actual = _load_counts(expected_path), _load_counts(actual_path)
    problems = compare_counts(expected, actual)
    for problem in problems:
        print(f"restore-check: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"restore-check: row counts match for {len(actual)} tables ({sum(actual.values())} rows)")
    return 0


def main(argv: Sequence[str] | None = None, clock: Clock = _utcnow) -> int:
    args = _parser().parse_args(argv)
    now = clock()
    if args.command == "name":
        print(backup_name(now, args.label))
        return 0
    if args.command == "due":
        taken = [b.taken_at for n in _backups(args.dir) if (b := parse_name(n)) is not None]
        return 0 if is_due(now, args.at, args.tz, taken) else 1
    if args.command == "latest":
        backups = [b for n in _backups(args.dir) if (b := parse_name(n)) is not None]
        if not backups:
            print(f"no backups in {args.dir}", file=sys.stderr)
            return 1
        print(args.dir / max(backups, key=lambda b: (b.taken_at, b.name)).name)
        return 0
    if args.command == "prune":
        return _prune(args.dir, now, args.dry_run)
    return _compare(args.expected, args.actual)


if __name__ == "__main__":
    sys.exit(main())
