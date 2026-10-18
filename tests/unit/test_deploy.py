"""P7.5: scripts/deploy.sh (make deploy / make rollback) against stub git, gh, docker and curl.

The docker stub keeps a tiny fake world in files: the database revision (`alembic current`,
`upgrade`, `downgrade` change it) and the image tag of the running containers (`up -d` sets it).
The curl stub fails the smoke test while a "broken" tag runs. Nothing touches the machine.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.shell import ROOT, Mac
from tests.support.shell import write as _write

DEPLOY = ROOT / "scripts" / "deploy.sh"
MAC_PROD = ROOT / "scripts" / "mac-prod.sh"

OLD_SHA = "0123456789abcdef0123456789abcdef01234567"
NEW_SHA = "fedcba9876543210fedcba9876543210fedcba98"
OLD_TAG = OLD_SHA[:12]
NEW_TAG = NEW_SHA[:12]
API_KEY = "smoke-test-key"
BOT_TOKEN = "123:bot-token-for-tests"


class Deployer(Mac):
    @property
    def world(self) -> Path:
        return self.tmp / "world"

    @property
    def state_dir(self) -> Path:
        return self.tmp / "state"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "deploy-state"

    @property
    def deploy_log(self) -> Path:
        return self.tmp / "logs" / "deploys.log"

    def set_world(self, name: str, value: str) -> None:
        _write(self.world / name, value + "\n")

    def get_world(self, name: str) -> str:
        return (self.world / name).read_text(encoding="utf-8").strip()

    def state(self) -> dict[str, str]:
        lines = self.state_file.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    def write_state(self, **values: str) -> None:
        _write(self.state_file, "".join(f"{key}={value}\n" for key, value in values.items()))

    def deploy(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return self.run(DEPLOY, *args, **self.env(**env))

    def env(self, **env: str) -> dict[str, str]:
        return {
            "TRAINSYNC_STATE_DIR": str(self.state_dir),
            "TRAINSYNC_LOG_DIR": str(self.tmp / "logs"),
            "TRAINSYNC_PYTHON": sys.executable,
            "WORLD": str(self.world),
            **env,
        }

    def compose_calls(self) -> list[str]:
        return [line for line in self.call_lines() if line.startswith("compose[")]

    def log_lines(self) -> list[str]:
        if not self.deploy_log.exists():
            return []
        return self.deploy_log.read_text(encoding="utf-8").splitlines()


GIT_STUB = """case "$*" in
  "status --porcelain") cat "$WORLD/dirty" 2>/dev/null ;;
  "rev-parse --abbrev-ref HEAD") cat "$WORLD/branch" ;;
  "rev-parse origin/main") cat "$WORLD/origin" ;;
  *"rev-parse HEAD") cat "$WORLD/head" ;;
esac"""

GH_STUB = 'cat "$WORLD/ci"'

# Every compose call is logged as `compose[<tag>] <args after the compose file>`.
DOCKER_STUB = """args="$*"
case "$args" in
  "image inspect"*) [ -f "$WORLD/image-missing" ] && exit 1; exit 0 ;;
esac
echo "compose[$TRAINSYNC_TAG] ${args#*compose.prod.yml }" >> "$STUB_CALLS"
case "$args" in
  *" ps --format"*) [ -f "$WORLD/running" ] && echo "trainsync:$(cat "$WORLD/running")" ;;
  *"alembic current")
    echo "INFO  [alembic.runtime.migration] Context impl PostgresqlImpl."
    rev=$(cat "$WORLD/db")
    if [ "$rev" = "$(cat "$WORLD/head-rev")" ]; then echo "$rev (head)"
    elif [ "$rev" != base ]; then echo "$rev"; fi ;;
  *"alembic downgrade "*) echo "${args##* }" > "$WORLD/db" ;;
  *"run --rm migrate") cat "$WORLD/head-rev" > "$WORLD/db" ;;
  *" up -d") echo "$TRAINSYNC_TAG" > "$WORLD/running" ;;
esac"""

# Smoke checks fail while the "broken" tag runs. The curl config (stdin) is kept per call.
CURL_STUB = """case "$*" in *"-K -"*)
  n=$(ls "$WORLD"/curl-config-* 2>/dev/null | wc -l | tr -d ' ')
  cat > "$WORLD/curl-config-$n" ;;
esac
running=$(cat "$WORLD/running" 2>/dev/null)
if [ -f "$WORLD/broken" ] && [ "$running" = "$(cat "$WORLD/broken")" ]; then
  exit 22
fi
exit 0"""


@pytest.fixture
def mac(tmp_path: Path) -> Deployer:
    """A Mac on clean main == origin/main, green CI, OLD running at revision 0008."""
    machine = Deployer(tmp_path)
    machine.home.mkdir()
    _write(machine.env_file, f"TRAINSYNC_TAG=\nGATEWAY_PORT=8080\nAPI_KEYS={API_KEY},second\n")
    machine.set_world("branch", "main")
    machine.set_world("head", NEW_SHA)
    machine.set_world("origin", NEW_SHA)
    machine.set_world("ci", "completed success")
    machine.set_world("db", "0008")
    machine.set_world("head-rev", "0009")
    machine.set_world("running", OLD_TAG)
    machine.write_state(
        current_sha=OLD_SHA,
        current_tag=OLD_TAG,
        current_rev="0008",
        previous_sha="",
        previous_tag="",
        previous_rev="",
        backup_label="",
    )
    machine.stub("git", GIT_STUB)
    machine.stub("gh", GH_STUB)
    machine.stub("docker", DOCKER_STUB)
    machine.stub("curl", CURL_STUB)
    machine.stub("sleep")
    return machine


# ------------------------------------------------------------------------------- preflight


@pytest.mark.parametrize(
    ("world", "value", "reason"),
    [
        ("dirty", " M src/trainsync/main.py", "uncommitted changes"),
        ("branch", "p7-deploy", "on branch 'p7-deploy', not main"),
        ("origin", OLD_SHA, f"is not origin/main {OLD_SHA}"),
        ("ci", "in_progress ", "CI for"),
        ("ci", "completed failure", "'completed failure', not 'completed success'"),
        ("ci", "", "no CI run"),
    ],
)
def test_deploy_refuses_before_touching_anything(
    mac: Deployer, world: str, value: str, reason: str
) -> None:
    mac.set_world(world, value)
    result = mac.deploy("deploy")
    assert result.returncode == 1, result.stdout + result.stderr
    assert reason in result.stdout
    assert mac.compose_calls() == []
    assert mac.state()["current_tag"] == OLD_TAG
    assert "refused" in mac.log_lines()[-1]


def test_deploy_asks_ci_about_the_head_sha(mac: Deployer) -> None:
    mac.set_world("ci", "completed failure")
    mac.deploy("deploy")
    gh = next(line for line in mac.call_lines() if line.startswith("gh "))
    assert f"run list --commit {NEW_SHA} --workflow ci" in gh
    assert "--json status,conclusion" in gh
    assert "git fetch --quiet origin main" in mac.call_lines()


def test_deploy_refuses_without_an_env_file(mac: Deployer) -> None:
    mac.env_file.unlink()
    result = mac.deploy("deploy")
    assert result.returncode == 1
    assert "is missing" in result.stdout


# ------------------------------------------------------------------------------ happy path


def test_deploy_builds_backs_up_migrates_starts_and_smoke_tests(mac: Deployer) -> None:
    result = mac.deploy("deploy")
    assert result.returncode == 0, result.stdout + result.stderr
    assert mac.compose_calls() == [
        f"compose[{NEW_TAG}] build",
        f"compose[{NEW_TAG}] run --rm backup now predeploy{NEW_SHA[:7]}",
        f"compose[{NEW_TAG}] --profile migrate run --rm -T migrate alembic current",
        f"compose[{NEW_TAG}] --profile migrate run --rm migrate",
        f"compose[{NEW_TAG}] --profile migrate run --rm -T migrate alembic current",
        f"compose[{NEW_TAG}] up -d",
    ]
    assert "database revision 0008 -> 0009" in result.stdout
    curls = [line for line in mac.call_lines() if line.startswith("curl ")]
    assert "http://127.0.0.1:8080/health/ready" in curls[0]
    assert curls[1].endswith("http://127.0.0.1:8080/v1/sync/status")
    assert len(curls) == 2  # no Telegram token: no getMe, no message
    # The API key reaches curl through its config on stdin, never on the command line.
    assert f'header = "X-API-Key: {API_KEY}"' in mac.get_world("curl-config-0")
    assert API_KEY not in "\n".join(mac.call_lines())
    assert mac.state() | {"updated_at": ""} == {
        "current_sha": NEW_SHA,
        "current_tag": NEW_TAG,
        "current_rev": "0009",
        "previous_sha": OLD_SHA,
        "previous_tag": OLD_TAG,
        "previous_rev": "0008",
        "backup_label": f"predeploy{NEW_SHA[:7]}",
        "updated_at": "",
    }
    assert mac.log_lines()[-1].endswith(f"deploy {NEW_SHA} success")
    assert not (mac.state_dir / "deploy.lock").exists()


def test_deploy_checks_the_bot_and_reports_to_telegram_when_configured(mac: Deployer) -> None:
    _write(
        mac.env_file,
        f"API_KEYS={API_KEY}\nTELEGRAM_BOT_TOKEN={BOT_TOKEN}\nTELEGRAM_ALLOWED_CHAT_IDS=42,43\n",
    )
    result = mac.deploy("deploy")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "smoke: Telegram getMe ok" in result.stdout
    configs = sorted(mac.world.glob("curl-config-*"), key=lambda p: int(p.name.split("-")[-1]))
    texts = [path.read_text(encoding="utf-8") for path in configs]
    assert f"bot{BOT_TOKEN}/getMe" in texts[1]
    assert f"bot{BOT_TOKEN}/sendMessage" in texts[2]
    message = [line for line in mac.call_lines() if line.startswith("curl ")][3]
    assert "chat_id=42" in message
    assert f"text=trainsync: deployed {NEW_TAG}" in message
    assert BOT_TOKEN not in "\n".join(mac.call_lines())


def test_deploy_waits_for_readiness(mac: Deployer) -> None:
    counter = mac.world / "ready-count"
    mac.stub(
        "curl",
        'case "$*" in *"-K -"*) cat > /dev/null ;; esac\n'
        'case "$*" in *health/ready*)\n'
        f'  n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "{counter}"\n'
        '  [ "$n" -ge 3 ]; exit $? ;;\n'
        "esac",
    )
    result = mac.deploy("deploy", SMOKE_INTERVAL_SECONDS="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert mac.call_lines().count("sleep 1") == 2


def test_first_deploy_takes_the_running_tag_as_the_rollback_target(mac: Deployer) -> None:
    mac.state_file.unlink()
    result = mac.deploy("deploy")
    assert result.returncode == 0, result.stdout + result.stderr
    assert mac.state()["previous_tag"] == OLD_TAG
    assert mac.state()["previous_rev"] == "0008"


def test_a_failed_migration_aborts_and_leaves_the_old_version_running(mac: Deployer) -> None:
    failing = DOCKER_STUB.replace('*"run --rm migrate") cat', '*"run --rm migrate") exit 1; cat')
    mac.stub("docker", failing)
    result = mac.deploy("deploy")
    assert result.returncode == 1
    assert "FAILED: migrations" in result.stdout
    assert not any(call.endswith("up -d") for call in mac.compose_calls())
    assert mac.state()["current_tag"] == OLD_TAG
    assert mac.log_lines()[-1].endswith(f"deploy {NEW_SHA} failed: migrations")


def test_a_failed_backup_stops_the_deploy_before_migrations(mac: Deployer) -> None:
    failing = DOCKER_STUB.replace(
        'case "$args" in\n  *" ps', 'case "$args" in\n  *"backup now"*) exit 1 ;;\n  *" ps'
    )
    mac.stub("docker", failing)
    result = mac.deploy("deploy")
    assert result.returncode == 1
    assert "FAILED: pre-deploy backup" in result.stdout
    assert not any("migrate" in call for call in mac.compose_calls())


# ------------------------------------------------------------------- automatic rollback


def test_smoke_failure_rolls_back_automatically(mac: Deployer) -> None:
    mac.set_world("broken", NEW_TAG)
    result = mac.deploy("deploy")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "smoke test FAILED" in result.stdout
    calls = mac.compose_calls()
    up_new = calls.index(f"compose[{NEW_TAG}] up -d")
    assert calls[up_new + 1 :] == [
        f"compose[{NEW_TAG}] --profile migrate run --rm migrate alembic downgrade 0008",
        f"compose[{OLD_TAG}] up -d",
    ]
    assert mac.get_world("db") == "0008"
    assert mac.get_world("running") == OLD_TAG
    assert mac.state()["current_tag"] == OLD_TAG
    assert mac.state()["current_rev"] == "0008"
    assert mac.state()["previous_tag"] == ""
    log = mac.log_lines()
    assert log[-2].endswith(f"deploy {NEW_SHA} failed: smoke test, rolling back")
    assert log[-1].endswith(f"rollback {OLD_SHA} success (auto, from {NEW_TAG})")


# ------------------------------------------------------------------------- manual rollback


def deployed(mac: Deployer) -> Deployer:
    result = mac.deploy("deploy")
    assert result.returncode == 0, result.stdout + result.stderr
    mac.calls.unlink()
    return mac


def test_rollback_downgrades_reversible_migrations_before_starting_the_old_images(
    mac: Deployer,
) -> None:
    result = deployed(mac).deploy("rollback")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0009 reversible" in result.stdout
    assert mac.compose_calls() == [
        f"compose[{NEW_TAG}] --profile migrate run --rm migrate alembic downgrade 0008",
        f"compose[{OLD_TAG}] up -d",
    ]
    assert mac.state()["current_sha"] == OLD_SHA
    assert mac.log_lines()[-1].endswith(f"rollback {OLD_SHA} success (manual, from {NEW_TAG})")


def test_rollback_without_crossed_migrations_only_swaps_images(mac: Deployer) -> None:
    mac.set_world("head-rev", "0008")
    result = deployed(mac).deploy("rollback")
    assert result.returncode == 0, result.stdout + result.stderr
    assert mac.compose_calls() == [f"compose[{OLD_TAG}] up -d"]


def test_rollback_across_a_non_reversible_migration_refuses_and_prints_the_restore(
    mac: Deployer,
) -> None:
    versions = mac.tmp / "versions"
    shutil.copytree(ROOT / "migrations" / "versions", versions)
    target = versions / "0009_workout_client_id.py"
    target.write_text(
        target.read_text(encoding="utf-8").replace("reversible: bool = True", "reversible = False"),
        encoding="utf-8",
    )
    deployed(mac)
    result = mac.deploy("rollback", TRAINSYNC_MIGRATIONS_DIR=str(versions))
    assert result.returncode == 1
    assert "0009 NOT reversible" in result.stdout
    assert "not reversible" in result.stdout
    assert f"-predeploy{NEW_SHA[:7]}.dump.age" in result.stdout
    assert "scripts/restore-check.sh" in result.stdout
    assert "docs/operations.md" in result.stdout
    assert "scripts/deploy.sh rollback --restored" in result.stdout
    assert mac.compose_calls() == []
    assert mac.state()["current_tag"] == NEW_TAG
    assert mac.log_lines()[-1].endswith(f"rollback {NEW_SHA} refused: non-reversible migration")

    # After the owner restored the pre-deploy backup.
    mac.set_world("db", "0008")
    result = mac.deploy("rollback", "--restored", TRAINSYNC_MIGRATIONS_DIR=str(versions))
    assert result.returncode == 0, result.stdout + result.stderr
    assert mac.compose_calls() == [f"compose[{OLD_TAG}] up -d"]


def test_rollback_refuses_without_a_previous_deploy(mac: Deployer) -> None:
    result = mac.deploy("rollback")
    assert result.returncode == 1
    assert "no previous deploy recorded" in result.stdout
    assert mac.compose_calls() == []


def test_rollback_refuses_when_the_old_image_is_gone(mac: Deployer) -> None:
    deployed(mac).set_world("image-missing", "1")
    result = mac.deploy("rollback")
    assert result.returncode == 1
    assert f"git switch --detach {OLD_SHA}" in result.stdout
    assert mac.compose_calls() == []


def test_rollback_refuses_when_the_checkout_moved(mac: Deployer) -> None:
    deployed(mac).set_world("head", OLD_SHA)
    result = mac.deploy("rollback")
    assert result.returncode == 1
    assert f"git switch --detach {NEW_SHA}" in result.stdout
    assert mac.compose_calls() == []


def test_rollback_is_one_step(mac: Deployer) -> None:
    deployed(mac).deploy("rollback")
    result = mac.deploy("rollback")
    assert result.returncode == 1
    assert "no previous deploy recorded" in result.stdout


def test_a_running_deploy_blocks_another(mac: Deployer) -> None:
    (mac.state_dir / "deploy.lock").mkdir(parents=True)
    result = mac.deploy("deploy")
    assert result.returncode == 1
    assert "another deploy or rollback is running" in result.stdout


def test_status_and_usage(mac: Deployer) -> None:
    assert f"current_tag={OLD_TAG}" in mac.deploy("status").stdout
    result = mac.deploy("frobnicate")
    assert result.returncode == 2
    assert "rollback --restored" in result.stderr


def test_mac_prod_starts_the_tag_of_the_last_deploy(mac: Deployer) -> None:
    result = mac.run(MAC_PROD, "up", **mac.env())
    assert result.returncode == 0, result.stderr
    assert mac.compose_calls()[-1] == f"compose[{OLD_TAG}] up -d"
