"""`make restore-check-ci`, last step (P8.2): a backup taken before Phase 8 restores with the
backup image and then migrates cleanly to head, every row ending up with the owner (ADR 0035).

1. A database at revision 0014 (the last single-user schema) with the pre-Phase-8 seed.
2. `backup.sh now` on it, and `backup.sh restore-check` passes on that dump.
3. The dump, decrypted by the image's age, restored into an empty database; `alembic upgrade head`
   with OWNER_EMAIL set; one owner account, and no owned row without it.

Imported by scripts/restore_check_ci.py, which owns the Postgres container and the keypair.
"""

import os
import subprocess
from pathlib import Path

import restore_check_ci as base

PRE_PHASE_REVISION = "0014"
SOURCE_DB, TARGET_DB = "prephase", "upgraded"
OWNER_EMAIL = "owner@restorecheck.invalid"
# The seed as it was before Phase 8: no users, no user_id columns.
LEGACY_SEED = """
INSERT INTO athletes (strava_athlete_id) VALUES (1001);
INSERT INTO activities (strava_activity_id, athlete_id, name, sport_type, start_date, distance_m,
                        moving_time_s, elapsed_time_s, elevation_gain_m, raw)
SELECT 5000 + g, (SELECT id FROM athletes), 'Run ' || g, 'Run', now() - g * interval '1 day',
       5000 + g, 1500, 1600, 20, jsonb_build_object('id', 5000 + g)
FROM generate_series(1, 30) AS g;
INSERT INTO workouts (client_id, started_at, notes)
SELECT gen_random_uuid(), now() - g * interval '2 days', 'session ' || g
FROM generate_series(1, 5) AS g;
INSERT INTO workout_sets (client_id, workout_id, exercise_id, set_index, reps, weight_kg,
                          completed_at)
SELECT gen_random_uuid(), w.id, (SELECT min(id) FROM exercises), s, 5, 60 + s, w.started_at
FROM workouts AS w, generate_series(1, 3) AS s;
INSERT INTO body_metrics (date, weight_kg)
SELECT current_date - g, 80 - g * 0.1 FROM generate_series(1, 7) AS g;
INSERT INTO daily_checkins (date, status)
SELECT current_date - g, 'done' FROM generate_series(1, 4) AS g;
"""
OWNED = ("athletes", "activities", "workouts", "workout_sets", "body_metrics", "daily_checkins")


def _psql(database: str, sql: str, *, tuples: bool = False) -> str:
    command = ["docker", "exec", "-i", base.PG, "psql", "-U", "trainsync", "-d", database]
    command += ["-v", "ON_ERROR_STOP=1", "-q", *(["-tA"] if tuples else [])]
    result = subprocess.run(command, input=sql, capture_output=True, text=True)
    if result.returncode != 0:
        base.fail(f"psql on {database}: {result.stderr.strip()}")
    return result.stdout.strip()


def _url(database: str) -> str:
    published = base.run("docker", "port", base.PG, "5432/tcp").strip().splitlines()[0]
    host, port = published.rsplit(":", 1)
    return f"postgresql+asyncpg://trainsync:{base.PG_PASSWORD}@{host}:{port}/{database}"


def _migrate(database: str, revision: str) -> None:
    env = {**os.environ, "DATABASE_URL": _url(database), "OWNER_EMAIL": OWNER_EMAIL}
    base.run("uv", "run", "alembic", "upgrade", revision, env=env)


def _restore(dump: Path, identity: Path, database: str) -> None:
    decrypt = ["docker", "run", "--rm", "--entrypoint", "age"]
    decrypt += ["-v", f"{dump.parent}:/backups:ro", "-v", f"{identity}:/run/identity:ro"]
    decrypt += [base.IMAGE, "-d", "-i", "/run/identity", f"/backups/{dump.name}"]
    plain = subprocess.run(decrypt, capture_output=True)
    if plain.returncode != 0:
        base.fail(f"decrypting the pre-phase dump: {plain.stderr.decode().strip()}")
    restore = ["docker", "exec", "-i", base.PG, "pg_restore", "-U", "trainsync", "-d", database]
    restore += ["--no-owner", "--no-acl", "--exit-on-error"]
    result = subprocess.run(restore, input=plain.stdout, capture_output=True)
    if result.returncode != 0:
        base.fail(f"pg_restore of the pre-phase dump: {result.stderr.decode().strip()}")


def check_pre_phase_upgrade(work: Path, recipient: str, identity: Path) -> None:
    for database in (SOURCE_DB, TARGET_DB):
        _psql("trainsync", f"CREATE DATABASE {database};")
    _migrate(SOURCE_DB, PRE_PHASE_REVISION)
    _psql(SOURCE_DB, LEGACY_SEED)
    backups = base.private_dir(work, "prephase-backups")
    base.backup(
        "-e", f"PGDATABASE={SOURCE_DB}", "-e", "BACKUP_AGE_RECIPIENT=" + recipient,
        base.IMAGE, "now", mounts=[f"{backups}:/backups"],
    )  # fmt: skip
    (dump,) = sorted(backups.glob("trainsync-*.dump.age"))
    code, output = base.restore_check(backups, identity)
    if code != 0:
        base.fail(f"restore-check failed on the pre-phase backup:\n{output}")
    _restore(dump, identity, TARGET_DB)
    _migrate(TARGET_DB, "head")
    owners = _psql(TARGET_DB, "SELECT email FROM users WHERE role = 'owner';", tuples=True)
    if owners != OWNER_EMAIL:
        base.fail(f"the upgraded database has owners {owners!r}, want {OWNER_EMAIL}")
    orphans = {
        table: _psql(
            TARGET_DB,
            f"SELECT count(*) FROM {table} WHERE user_id IS DISTINCT FROM "  # noqa: S608  (constant names)
            "(SELECT id FROM users WHERE role = 'owner');",
            tuples=True,
        )
        for table in OWNED
    }
    if any(count != "0" for count in orphans.values()):
        fail_counts = {table: count for table, count in orphans.items() if count != "0"}
        base.fail(f"rows not given to the owner after the upgrade: {fail_counts}")
    print(f"  pre-phase backup (revision {PRE_PHASE_REVISION}) restores and migrates to head")
