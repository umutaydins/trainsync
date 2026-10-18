"""Which migrations lie between two Alembic revisions, and can a rollback undo them? (P7.5)

    python3 scripts/migration_reversibility.py FROM TO [--versions DIR]

FROM is the revision before a deploy (`base` for an empty database), TO the revision after it.
Prints one line per migration in (FROM, TO], oldest first, and exits 0 when every one of them
declares `reversible = True`, 1 when at least one declares `reversible = False`, 2 on an error
(unknown revision, TO not a descendant of FROM, a migration without a bool `reversible`).

Every migration file declares a module-level `reversible = True` or `False` (ADR 0026):
reversible means its `downgrade()` restores the previous revision's schema and keeps every row
the previous code can read; it may drop what only the new code wrote. The files are parsed, not
imported, so this runs with a bare `python3` on the host (scripts/deploy.sh rollback).
"""

import argparse
import ast
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
BASE = "base"


class MigrationError(Exception):
    """A migration file or a revision range that cannot be judged."""


@dataclass(frozen=True)
class Migration:
    revision: str
    down_revision: str | None
    reversible: bool
    path: Path


def _assigned(tree: ast.Module) -> dict[str, object]:
    """Module-level `name = <literal>` and `name: T = <literal>` assignments."""
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name):
            try:
                values[target.id] = ast.literal_eval(value)
            except ValueError:
                continue
    return values


def parse_migration(path: Path) -> Migration:
    values = _assigned(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    revision = values.get("revision")
    down_revision = values.get("down_revision")
    reversible = values.get("reversible")
    if not isinstance(revision, str):
        raise MigrationError(f"{path.name}: no string `revision`")
    if down_revision is not None and not isinstance(down_revision, str):
        raise MigrationError(f"{path.name}: `down_revision` must be a string or None")
    if not isinstance(reversible, bool):
        raise MigrationError(f"{path.name}: declare `reversible = True` or `reversible = False`")
    return Migration(revision, down_revision, reversible, path)


def load_migrations(versions: Path = DEFAULT_VERSIONS) -> dict[str, Migration]:
    migrations: dict[str, Migration] = {}
    for path in sorted(versions.glob("*.py")):
        if path.name.startswith("_"):
            continue
        migration = parse_migration(path)
        if migration.revision in migrations:
            raise MigrationError(f"revision {migration.revision} is declared twice")
        migrations[migration.revision] = migration
    return migrations


def between(migrations: dict[str, Migration], start: str, end: str) -> list[Migration]:
    """The migrations a database crosses going from `start` up to `end`, oldest first."""
    stop = None if start == BASE else start
    if stop is not None and stop not in migrations:
        raise MigrationError(f"unknown revision {start}")
    if end == BASE:
        if stop is None:
            return []
        raise MigrationError(f"{end} is not a descendant of {start}")
    if end not in migrations:
        raise MigrationError(f"unknown revision {end}")
    crossed: list[Migration] = []
    current: str | None = end
    while current != stop:
        if current is None:
            raise MigrationError(f"{end} is not a descendant of {start}")
        migration = migrations[current]
        crossed.append(migration)
        current = migration.down_revision
    return list(reversed(crossed))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("start", metavar="FROM")
    parser.add_argument("end", metavar="TO")
    parser.add_argument("--versions", type=Path, default=DEFAULT_VERSIONS)
    args = parser.parse_args(argv)
    try:
        crossed = between(load_migrations(args.versions), args.start, args.end)
    except MigrationError as exc:
        print(f"migration_reversibility: {exc}", file=sys.stderr)
        return 2
    for migration in crossed:
        flag = "reversible" if migration.reversible else "NOT reversible"
        print(f"{migration.revision} {flag} ({migration.path.name})")
    return 0 if all(m.reversible for m in crossed) else 1


if __name__ == "__main__":
    sys.exit(main())
