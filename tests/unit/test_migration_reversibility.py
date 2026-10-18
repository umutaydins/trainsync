"""P7.5: scripts/migration_reversibility.py and the `reversible` flag of every migration."""

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations" / "versions"


def _load() -> ModuleType:
    name = "migration_reversibility"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mr = _load()


def _copy(tmp_path: Path) -> Path:
    versions = tmp_path / "versions"
    shutil.copytree(VERSIONS, versions)
    return versions


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize("path", sorted(VERSIONS.glob("[0-9]*.py")), ids=lambda p: p.name)
def test_every_migration_declares_a_bool_reversible(path: Path) -> None:
    migration = mr.parse_migration(path)
    assert isinstance(migration.reversible, bool)
    assert path.name.startswith(migration.revision)


def test_the_migrations_form_one_chain_from_base() -> None:
    migrations = mr.load_migrations(VERSIONS)
    head = max(migrations)
    chain = mr.between(migrations, "base", head)
    assert [m.revision for m in chain] == sorted(migrations)


def test_between_lists_the_crossed_migrations_oldest_first() -> None:
    migrations = mr.load_migrations(VERSIONS)
    assert [m.revision for m in mr.between(migrations, "0006", "0009")] == ["0007", "0008", "0009"]
    assert mr.between(migrations, "0009", "0009") == []
    assert mr.between(migrations, "base", "base") == []


@pytest.mark.parametrize(
    ("start", "end", "error"),
    [
        ("0009", "0006", "not a descendant"),
        ("0042", "0009", "unknown revision 0042"),
        ("0006", "0042", "unknown revision 0042"),
        ("0006", "base", "not a descendant"),
    ],
)
def test_between_rejects_bad_ranges(start: str, end: str, error: str) -> None:
    with pytest.raises(mr.MigrationError, match=error):
        mr.between(mr.load_migrations(VERSIONS), start, end)


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    versions = _copy(tmp_path)
    assert mr.main(["0007", "0009", "--versions", str(versions)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "0008 reversible (0008_food_log_snapshot.py)",
        "0009 reversible (0009_workout_client_id.py)",
    ]
    _edit(versions / "0008_food_log_snapshot.py", "reversible: bool = True", "reversible = False")
    assert mr.main(["0007", "0009", "--versions", str(versions)]) == 1
    assert "0008 NOT reversible" in capsys.readouterr().out
    assert mr.main(["0009", "0007", "--versions", str(versions)]) == 2
    assert "not a descendant" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        ("reversible: bool = True", "", "declare `reversible = True`"),
        ("reversible: bool = True", 'reversible = "yes"', "declare `reversible = True`"),
        ('revision: str = "0009"', "revision = None", "no string `revision`"),
        ('down_revision: str | None = "0008"', "down_revision = 8", "`down_revision` must"),
    ],
)
def test_bad_declarations_are_errors(tmp_path: Path, old: str, new: str, error: str) -> None:
    versions = _copy(tmp_path)
    _edit(versions / "0009_workout_client_id.py", old, new)
    with pytest.raises(mr.MigrationError, match=error):
        mr.load_migrations(versions)
    assert mr.main(["0008", "0009", "--versions", str(versions)]) == 2


def test_a_duplicate_revision_is_an_error(tmp_path: Path) -> None:
    versions = _copy(tmp_path)
    shutil.copy(versions / "0009_workout_client_id.py", versions / "0010_copy.py")
    with pytest.raises(mr.MigrationError, match="declared twice"):
        mr.load_migrations(versions)
