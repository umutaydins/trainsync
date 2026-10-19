"""`make restore-check-ci` (P7.4): back up a seeded database with the backup image and prove the
restore check passes on a good backup and fails on a bad one. Docker only, no secrets: the age
keypair is generated inside the image for this run and deleted afterwards.

1. Build the backup image; start Postgres 16 on a private network; migrate (alembic) and seed.
2. `backup.sh now`: one encrypted dump + .counts.json sidecar; the counts match the seed.
3. `backup.sh restore-check` passes on it.
4. It fails on: a truncated file, a flipped byte, a wrong identity, a sidecar that disagrees
   with the dump, a missing sidecar.
5. The loop: with the slot already passed today it backs up, runs the weekly restore check
   (today is the check day), and stops cleanly on `docker stop`.
6. Retention runs inside the image's Python.
7. A pre-Phase-8 backup restores and migrates to head (scripts/restore_upgrade.py).

    uv run python scripts/restore_check_ci.py [--keep]
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "trainsync-backup:restorecheck-ci"
NETWORK = "trainsync-restorecheck-ci"
PG = "trainsync-restorecheck-ci-pg"
LOOP = "trainsync-restorecheck-ci-loop"
PG_PASSWORD = "dev-only-restorecheck-password"  # noqa: S105  (throwaway CI database)
PG_ENV = ["-e", "PGHOST=" + PG, "-e", "PGUSER=trainsync", "-e", "PGDATABASE=trainsync"]
PG_ENV += ["-e", "PGPASSWORD=" + PG_PASSWORD]

SEED = """
INSERT INTO users (email, password_hash, display_name, role, timezone)
VALUES ('owner@restorecheck.invalid', 'not-a-hash', 'Owner', 'owner', 'UTC');
CREATE TEMP TABLE owner AS SELECT id FROM users;
INSERT INTO athletes (user_id, strava_athlete_id) VALUES ((SELECT id FROM owner), 1001);
INSERT INTO activities (user_id, strava_activity_id, athlete_id, name, sport_type, start_date,
                        distance_m, moving_time_s, elapsed_time_s, elevation_gain_m, raw)
SELECT (SELECT id FROM owner), 5000 + g, (SELECT id FROM athletes), 'Run ' || g, 'Run',
       now() - g * interval '1 day', 5000 + g, 1500, 1600, 20, jsonb_build_object('id', 5000 + g)
FROM generate_series(1, 120) AS g;
INSERT INTO workouts (user_id, client_id, started_at, notes)
SELECT (SELECT id FROM owner), gen_random_uuid(), now() - g * interval '2 days', 'session ' || g
FROM generate_series(1, 12) AS g;
INSERT INTO workout_sets (user_id, client_id, workout_id, exercise_id, set_index, reps,
                          weight_kg, completed_at)
SELECT w.user_id, gen_random_uuid(), w.id, (SELECT min(id) FROM exercises), s, 5, 60 + s,
       w.started_at
FROM workouts AS w, generate_series(1, 4) AS s;
INSERT INTO foods (user_id, name, kcal_100g) VALUES ((SELECT id FROM owner), 'Oats', 380);
INSERT INTO food_logs (user_id, client_id, date, meal, food_id, grams, kcal_100g)
SELECT (SELECT id FROM owner), gen_random_uuid(), current_date - g, 'breakfast',
       (SELECT id FROM foods), 80, 380
FROM generate_series(1, 15) AS g;
INSERT INTO body_metrics (user_id, date, weight_kg)
SELECT (SELECT id FROM owner), current_date - g, 80 - g * 0.1 FROM generate_series(1, 20) AS g;
INSERT INTO daily_checkins (user_id, date, status)
SELECT (SELECT id FROM owner), current_date - g, 'done' FROM generate_series(1, 9) AS g;
"""
EXPECTED = {
    "users": 1,
    "athletes": 1,
    "activities": 120,
    "workouts": 12,
    "workout_sets": 48,
    "food_logs": 15,
    "body_metrics": 20,
    "daily_checkins": 9,
}


def fail(message: str) -> None:
    print(f"restore-check-ci: FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*args: str, check: bool = True, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, env=env)
    if check and result.returncode != 0:
        fail(f"{' '.join(args[:6])}: {(result.stdout + result.stderr).strip()[-3000:]}")
    return result.stdout + result.stderr


def backup(*args: str, mounts: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["docker", "run", "--rm", "--network", NETWORK, *PG_ENV]
    for mount in mounts:
        command += ["-v", mount]
    command += [*args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        fail(f"backup {args[-2:]}: {(result.stdout + result.stderr).strip()[-3000:]}")
    return result


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_postgres() -> None:
    port = free_port()
    run("docker", "network", "create", NETWORK)
    run(
        "docker", "run", "-d", "--name", PG, "--network", NETWORK,
        "-p", f"127.0.0.1:{port}:5432",
        "-e", "POSTGRES_USER=trainsync", "-e", "POSTGRES_PASSWORD=" + PG_PASSWORD,
        "-e", "POSTGRES_DB=trainsync", "postgres:16-alpine",
    )  # fmt: skip
    for _ in range(60):
        ready = ["docker", "exec", PG, "pg_isready", "-U", "trainsync", "-h", "127.0.0.1"]
        if subprocess.run(ready, capture_output=True).returncode == 0:
            break
        time.sleep(1)
    else:
        fail("Postgres did not become ready")
    url = f"postgresql+asyncpg://trainsync:{PG_PASSWORD}@127.0.0.1:{port}/trainsync"
    run("uv", "run", "alembic", "upgrade", "head", env={**os.environ, "DATABASE_URL": url})
    psql = ["docker", "exec", "-i", PG, "psql", "-U", "trainsync", "-v", "ON_ERROR_STOP=1", "-q"]
    seeded = subprocess.run(psql, input=SEED, capture_output=True, text=True)
    if seeded.returncode != 0:
        fail(f"seed: {seeded.stderr}")
    print("  postgres: migrated and seeded")


def age_keygen() -> str:
    """The identity file text (stdout only: age-keygen repeats the public key on stderr)."""
    command = ["docker", "run", "--rm", "--entrypoint", "age-keygen", IMAGE]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        fail(f"age-keygen: {result.stderr}")
    return result.stdout


def keypair(work: Path) -> tuple[str, Path]:
    """A throwaway age keypair for this run (never written to the repo)."""
    out = age_keygen()
    identity = work / "identity.txt"
    identity.write_text(out, encoding="utf-8")
    identity.chmod(0o644)  # the image runs as the postgres user, not as the host user
    recipient = next(line.split(": ", 1)[1] for line in out.splitlines() if "public key" in line)
    return recipient.strip(), identity


def private_dir(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir()
    path.chmod(0o777)  # writable by the image's postgres user on Linux CI
    return path


def check_backup(backups: Path, recipient: str) -> Path:
    backup(
        "-e", "BACKUP_AGE_RECIPIENT=" + recipient, IMAGE, "now",
        mounts=[f"{backups}:/backups"],
    )  # fmt: skip
    dumps = sorted(backups.glob("trainsync-*.dump.age"))
    if len(dumps) != 1 or list(backups.glob(".*")):
        fail(f"expected one finished backup and no temp files, got {sorted(os.listdir(backups))}")
    dump = dumps[0]
    if dump.read_bytes()[:21] != b"age-encryption.org/v1":
        fail("the backup is not an age file")
    counts = json.loads(dump.with_name(dump.name.replace(".dump.age", ".counts.json")).read_text())
    wrong = {t: (n, counts.get(t)) for t, n in EXPECTED.items() if counts.get(t) != n}
    if wrong:
        fail(f"sidecar counts differ from the seed (want, got): {wrong}")
    print(f"  backup: {dump.name}, {dump.stat().st_size} bytes, counts match the seed")
    return dump


def restore_check(directory: Path, identity: Path, name: str = "latest") -> tuple[int, str]:
    target = name if name == "latest" else f"/backups/{name}"
    result = backup(
        IMAGE, "restore-check", target,
        mounts=[f"{directory}:/backups:ro", f"{identity}:/run/secrets/backup_identity:ro"],
        check=False,
    )  # fmt: skip
    return result.returncode, result.stdout + result.stderr


def expect_failure(label: str, directory: Path, identity: Path, needle: str) -> None:
    code, output = restore_check(directory, identity)
    if code == 0:
        fail(f"restore-check passed on {label}:\n{output}")
    if needle not in output:
        fail(f"restore-check on {label} failed for another reason (wanted {needle!r}):\n{output}")
    print(f"  bad backup rejected: {label}")


def copy_case(work: Path, name: str, dump: Path) -> tuple[Path, Path, Path]:
    case = private_dir(work, name)
    target = case / dump.name
    counts_src = dump.with_name(dump.name.replace(".dump.age", ".counts.json"))
    shutil.copy(dump, target)
    shutil.copy(counts_src, case / counts_src.name)
    return case, target, case / counts_src.name


def check_bad_backups(work: Path, dump: Path, identity: Path) -> None:
    case, target, _ = copy_case(work, "truncated", dump)
    target.write_bytes(dump.read_bytes()[: dump.stat().st_size // 2])
    expect_failure("a truncated file", case, identity, "decryption failed")

    case, target, _ = copy_case(work, "flipped", dump)
    data = bytearray(dump.read_bytes())
    data[len(data) // 2] ^= 0x01
    target.write_bytes(bytes(data))
    expect_failure("a flipped byte", case, identity, "decryption failed")

    other = work / "other-identity.txt"
    other.write_text(age_keygen())
    other.chmod(0o644)
    case, _, _ = copy_case(work, "wrong-key", dump)
    expect_failure("a wrong identity", case, other, "decryption failed")

    case, _, counts = copy_case(work, "counts", dump)
    data_counts = json.loads(counts.read_text())
    data_counts["activities"] += 1
    counts.write_text(json.dumps(data_counts))
    expect_failure("a sidecar that disagrees", case, identity, "activities: backup recorded 121")

    case, _, counts = copy_case(work, "no-sidecar", dump)
    counts.unlink()
    expect_failure("a missing sidecar", case, identity, "missing row-count sidecar")


def check_loop(work: Path, recipient: str, identity: Path) -> None:
    backups = private_dir(work, "loop")
    weekday = str(datetime.now(UTC).isoweekday())
    run(
        "docker", "run", "-d", "--name", LOOP, "--network", NETWORK, *PG_ENV,
        "-e", "BACKUP_AGE_RECIPIENT=" + recipient, "-e", "BACKUP_TIME=00:00",
        "-e", "BACKUP_TZ=UTC", "-e", "RESTORE_CHECK_WEEKDAY=" + weekday,
        "-e", "BACKUP_POLL_SECONDS=1",
        "-v", f"{backups}:/backups", "-v", f"{identity}:/run/secrets/backup_identity:ro",
        IMAGE, "loop",
    )  # fmt: skip
    logs = ""
    for _ in range(120):
        logs = run("docker", "logs", LOOP)
        if "weekly restore check" in logs:
            break
        time.sleep(1)
    started = time.monotonic()
    run("docker", "stop", "-t", "20", LOOP)
    stop_seconds = time.monotonic() - started
    logs = run("docker", "logs", LOOP)
    run("docker", "rm", LOOP)
    if "weekly restore check passed" not in logs or "Telegram not configured, skipped" not in logs:
        fail(f"the loop did not back up and pass its weekly restore check:\n{logs}")
    if logs.count("wrote trainsync-") != 1:
        fail(f"the loop took more than one backup for one slot:\n{logs}")
    if "stopping" not in logs or stop_seconds > 10:
        fail(f"the loop did not stop on SIGTERM ({stop_seconds:.0f} s):\n{logs}")
    print("  loop: one backup for the slot, weekly restore check passed, clean stop")


def check_retention(work: Path) -> None:
    backups = private_dir(work, "retention")
    now = datetime.now(UTC)
    for days in range(0, 400, 3):
        stamp = (now - timedelta(days=days)).strftime("%Y%m%d-%H%M%S")
        for suffix in (".dump.age", ".counts.json"):
            (backups / f"trainsync-{stamp}{suffix}").write_text("x")
    (backups / "notes.txt").write_text("not a backup")
    before = len(list(backups.glob("*.dump.age")))
    backup(IMAGE, "prune", mounts=[f"{backups}:/backups"])
    after = sorted(p.name for p in backups.glob("*.dump.age"))
    sidecars = len(list(backups.glob("*.counts.json")))
    if not 7 <= len(after) <= 17 or sidecars != len(after) or not (backups / "notes.txt").exists():
        fail(f"retention kept {len(after)} of {before} ({sidecars} sidecars): {after}")
    print(f"  retention in the image: kept {len(after)} of {before}, sidecars with them")


def cleanup() -> None:
    for container in (LOOP, PG):
        subprocess.run(["docker", "rm", "-f", "-v", container], capture_output=True)
    subprocess.run(["docker", "network", "rm", NETWORK], capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="leave the containers and files")
    args = parser.parse_args()
    cleanup()
    work = Path(tempfile.mkdtemp(prefix="restorecheck-ci-"))
    try:
        print("restore-check-ci: build")
        run("docker", "build", "-q", "-t", IMAGE, "-f", "deploy/backup/Dockerfile", ".")
        start_postgres()
        recipient, identity = keypair(work)
        dump = check_backup(private_dir(work, "backups"), recipient)
        code, output = restore_check(dump.parent, identity)
        if code != 0 or "row counts match" not in output:
            fail(f"restore-check failed on a good backup:\n{output}")
        print("  " + next(line for line in output.splitlines() if "row counts match" in line))
        check_bad_backups(work, dump, identity)
        check_loop(work, recipient, identity)
        check_retention(work)
        from restore_upgrade import check_pre_phase_upgrade  # imports this module back

        check_pre_phase_upgrade(work, recipient, identity)
    finally:
        if not args.keep:
            cleanup()
            shutil.rmtree(work, ignore_errors=True)
    print("restore-check-ci: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
