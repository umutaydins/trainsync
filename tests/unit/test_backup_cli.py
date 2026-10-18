"""The backup container's decisions (P7.4, ADR 0024): when a backup is due, the newest backup,
pruning files, comparing row counts. Plus: trainsync.ops stays standard-library only."""

import ast
import json
import sys
from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import trainsync.ops
from trainsync.ops import backup_cli
from trainsync.ops.backup_cli import KEY_TABLES, compare_counts, is_due, main

IST = ZoneInfo("Europe/Istanbul")  # UTC+3, slot 03:30 local = 00:30 UTC
SLOT = time(3, 30)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def clock(text: str) -> backup_cli.Clock:
    return lambda: utc(text)


def test_not_due_before_the_slot() -> None:
    assert not is_due(utc("2026-10-18T00:29:00"), SLOT, IST, [])


def test_due_after_the_slot_until_a_backup_is_taken() -> None:
    assert is_due(utc("2026-10-18T00:31:00"), SLOT, IST, [utc("2026-10-17T00:30:00")])
    assert not is_due(utc("2026-10-18T09:00:00"), SLOT, IST, [utc("2026-10-18T00:31:00")])


def test_a_backup_before_the_slot_does_not_count() -> None:
    predeploy = utc("2026-10-17T23:00:00")  # 02:00 local, before today's slot
    assert is_due(utc("2026-10-18T01:00:00"), SLOT, IST, [predeploy])


def test_a_mac_that_slept_through_the_slot_backs_up_on_wake() -> None:
    assert is_due(utc("2026-10-18T20:00:00"), SLOT, IST, [utc("2026-10-17T00:30:00")])


def test_compare_counts() -> None:
    counts = dict.fromkeys(KEY_TABLES, 3) | {"alembic_version": 1}
    assert compare_counts(counts, counts) == []
    assert compare_counts(counts, counts | {"activities": 2}) == [
        "activities: backup recorded 3, restore has 2"
    ]
    without = {k: v for k, v in counts.items() if k != "workouts"}
    assert compare_counts(without, without) == ["workouts: missing from the restored database"]
    assert compare_counts(counts, counts | {"extra": 0}) == [
        "extra: backup recorded None, restore has 0"
    ]


def test_name(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["name"], clock("2026-10-18T00:30:05")) == 0
    assert main(["name", "--label", "predeploy"], clock("2026-10-18T00:30:05")) == 0
    assert capsys.readouterr().out.split() == [
        "trainsync-20261018-003005.dump.age",
        "trainsync-20261018-003005-predeploy.dump.age",
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["name", "--label", "Pre Deploy"],
        ["due", "--dir", ".", "--at", "25:00", "--tz", "UTC"],
        ["due", "--dir", ".", "--at", "03:30", "--tz", "Mars/Olympus"],
    ],
)
def test_usage_errors_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_due_reads_the_directory(tmp_path: Path) -> None:
    argv = ["due", "--dir", str(tmp_path), "--at", "03:30", "--tz", "Europe/Istanbul"]
    assert main(argv, clock("2026-10-18T01:00:00")) == 0
    (tmp_path / "trainsync-20261018-003100.dump.age").write_text("x")
    assert main(argv, clock("2026-10-18T01:00:00")) == 1


def test_latest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["latest", "--dir", str(tmp_path)]) == 1
    for n in (
        "trainsync-20261017-003000.dump.age",
        "trainsync-20261018-003000.dump.age",
        "trainsync-20261018-003000.counts.json",
        "zzz.dump.age",
    ):
        (tmp_path / n).write_text("x")
    capsys.readouterr()
    assert main(["latest", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "trainsync-20261018-003000.dump.age")


def test_prune_deletes_dumps_with_their_sidecars(tmp_path: Path) -> None:
    for day in ("20261018-003000", "20261018-001000"):
        (tmp_path / f"trainsync-{day}.dump.age").write_text("x")
        (tmp_path / f"trainsync-{day}.counts.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("keep me")
    now = clock("2026-10-18T12:00:00")

    assert main(["prune", "--dir", str(tmp_path), "--dry-run"], now) == 0
    assert len(list(tmp_path.iterdir())) == 5

    assert main(["prune", "--dir", str(tmp_path)], now) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "notes.txt",
        "trainsync-20261018-003000.counts.json",
        "trainsync-20261018-003000.dump.age",
    ]


def test_compare_counts_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    counts = dict.fromkeys(KEY_TABLES, 2)
    expected, actual = tmp_path / "expected.json", tmp_path / "actual.json"
    expected.write_text(json.dumps(counts))
    actual.write_text(json.dumps(counts))
    assert main(["compare-counts", str(expected), str(actual)]) == 0
    assert "row counts match for 7 tables (14 rows)" in capsys.readouterr().out

    actual.write_text(json.dumps(counts | {"food_logs": 1}))
    assert main(["compare-counts", str(expected), str(actual)]) == 1
    assert "food_logs: backup recorded 2, restore has 1" in capsys.readouterr().err

    actual.write_text("[1, 2]")
    with pytest.raises(ValueError, match="table -> row count"):
        main(["compare-counts", str(expected), str(actual)])


def test_ops_uses_only_the_standard_library() -> None:
    """The backup image runs these modules with a bare python3 (no app dependencies)."""
    package = Path(trainsync.ops.__file__).parent
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                top = module.split(".")[0]
                ok = top in sys.stdlib_module_names or module.startswith("trainsync.ops")
                assert ok, f"{path.name} imports {module}"
