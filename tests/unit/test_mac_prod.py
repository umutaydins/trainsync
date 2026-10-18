"""P7.2: scripts/mac-prod.sh and the LaunchAgent wrapper, run against stub commands.

Every external command the scripts use (docker, pmset, tailscale, df, curl, launchctl, fdesetup,
defaults, git, open, sleep) is a stub on a temporary PATH, and HOME is a temporary directory, so
nothing here touches the Mac it runs on.
"""

import atexit
import functools
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAC_PROD = ROOT / "scripts" / "mac-prod.sh"
START_STACK = ROOT / "deploy" / "macos" / "start-stack.sh"
TEMPLATE = ROOT / "deploy" / "macos" / "com.trainsync.stack.plist"
BASH = shutil.which("bash") or "/bin/bash"

PMSET_OK = """Battery Power:
 sleep                1
 disksleep            10
AC Power:
 sleep                0
 disksleep            0
"""
FUNNEL_ON = """# Funnel on:
#     - https://mac.tail1234.ts.net

https://mac.tail1234.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:8080
"""
# 200 GB free, in 1 KB blocks.
DF_OK = "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk3 1 1 209715200 1% /\n"


STUBBED = (
    "docker",
    "pmset",
    "df",
    "tailscale",
    "curl",
    "launchctl",
    "fdesetup",
    "defaults",
    "git",
    "open",
    "sleep",
)
# One dispatcher, linked under every stubbed name: it logs its call and runs the test's behavior
# file for that name. Created once per session, because macOS scans each new executable on its
# first run (seconds per file).
DISPATCHER = """#!/bin/sh
name=$(basename "$0")
echo "$name $*" >> "$STUB_CALLS"
if [ -f "$STUB_BEHAVIOR/$name" ]; then . "$STUB_BEHAVIOR/$name"; fi
exit 0
"""


@functools.cache
def _stub_bin() -> Path:
    bin_dir = Path(tempfile.mkdtemp(prefix="mac-prod-stubs-"))
    atexit.register(shutil.rmtree, bin_dir, True)
    dispatcher = bin_dir / "_stub"
    dispatcher.write_text(DISPATCHER, encoding="utf-8")
    dispatcher.chmod(0o755)
    for name in STUBBED:
        (bin_dir / name).symlink_to(dispatcher)
    return bin_dir


@dataclass
class Mac:
    tmp: Path
    stubs: dict[str, str] = field(default_factory=dict)

    @property
    def home(self) -> Path:
        return self.tmp / "home"

    @property
    def env_file(self) -> Path:
        return self.tmp / "env.prod"

    @property
    def calls(self) -> Path:
        return self.tmp / "calls.log"

    @property
    def backup_dir(self) -> Path:
        return self.home / "backups"

    def stub(self, name: str, body: str = "exit 0") -> None:
        self.stubs[name] = body

    def run(self, script: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        behavior = self.tmp / "behavior"
        behavior.mkdir(exist_ok=True)
        for name, body in self.stubs.items():
            (behavior / name).write_text(body + "\n", encoding="utf-8")
        full_env = {
            "PATH": f"{_stub_bin()}:/usr/bin:/bin",
            "STUB_BEHAVIOR": str(behavior),
            "STUB_CALLS": str(self.calls),
            "HOME": str(self.home),
            "TRAINSYNC_ENV_FILE": str(self.env_file),
            "BACKUP_DIR": str(self.backup_dir),
            **env,
        }
        return subprocess.run(  # noqa: S603  (our own scripts, fixed args)
            [BASH, str(script), *args],
            env=full_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def call_lines(self) -> list[str]:
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def mac(tmp_path: Path) -> Mac:
    """A Mac where every doctor check passes."""
    machine = Mac(tmp_path)
    machine.home.mkdir()
    _write(machine.env_file, "TRAINSYNC_TAG=abc123\nGATEWAY_PORT=8080\n")
    machine.env_file.chmod(0o600)
    _write(
        machine.home / "Library/Group Containers/group.com.docker/settings-store.json",
        '{\n  "AutoStart": true,\n  "Other": 1\n}\n',
    )
    _write(machine.home / "Library/LaunchAgents/com.trainsync.stack.plist", "<plist/>")
    _write(machine.backup_dir / "trainsync-20261017-030000.dump.age", "x")
    machine.stub(
        "docker", 'if [ "$1" = info ]; then exit 0; fi\necho "TAG=$TRAINSYNC_TAG" >> "$STUB_CALLS"'
    )
    machine.stub("pmset", f"cat <<'EOF'\n{PMSET_OK}EOF")
    machine.stub("df", f"printf '%s' '{DF_OK}'")
    machine.stub(
        "tailscale",
        'case "$1" in\n'
        '  status) echo \'{"BackendState": "Running"}\' ;;\n'
        f"  funnel) cat <<'EOF'\n{FUNNEL_ON}EOF\n ;;\n"
        "esac",
    )
    machine.stub("curl")
    machine.stub("launchctl")
    machine.stub("fdesetup", "echo 'FileVault is Off.'")
    machine.stub("defaults", "echo umut")
    machine.stub("git", "echo deadbeef1234")
    machine.stub("open")
    machine.stub("sleep")
    return machine


def test_doctor_all_green(mac: Mac) -> None:
    result = mac.run(MAC_PROD, "doctor")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout
    assert "WARN" not in result.stdout
    assert "doctor: OK (0 warnings)" in result.stdout


def _break_env_missing(mac: Mac) -> None:
    mac.env_file.unlink()


def _break_env_mode(mac: Mac) -> None:
    mac.env_file.chmod(0o644)


def _break_docker(mac: Mac) -> None:
    mac.stub("docker", "exit 1")


def _break_autostart(mac: Mac) -> None:
    _write(
        mac.home / "Library/Group Containers/group.com.docker/settings-store.json",
        '{"AutoStart": false}',
    )


def _break_sleep(mac: Mac) -> None:
    mac.stub("pmset", "printf 'AC Power:\\n sleep 1\\n disksleep 10\\n'")


def _break_disk(mac: Mac) -> None:
    mac.stub(
        "df", "printf 'Filesystem 1024-blocks Used Available\\n/dev/disk3 1 1 1048576 1%% /\\n'"
    )


def _break_tailscale(mac: Mac) -> None:
    mac.stub("tailscale", 'echo \'{"BackendState": "Stopped"}\'')


def _break_funnel(mac: Mac) -> None:
    mac.stub(
        "tailscale",
        'if [ "$1" = status ]; then echo \'{"BackendState": "Running"}\'; '
        "else echo 'No serve config'; fi",
    )


def _break_stack(mac: Mac) -> None:
    mac.stub("curl", "exit 7")


def _break_agent_missing(mac: Mac) -> None:
    (mac.home / "Library/LaunchAgents/com.trainsync.stack.plist").unlink()


def _break_agent_unloaded(mac: Mac) -> None:
    mac.stub("launchctl", "exit 113")


@pytest.mark.parametrize(
    ("breaker", "problem", "fix"),
    [
        (_break_env_missing, "is missing", "cp .env.prod.example .env.prod"),
        (_break_env_mode, "readable by others", "chmod 600"),
        (_break_docker, "Docker is not running", "open -a Docker"),
        (_break_autostart, "does not start at login", "Start Docker Desktop when you sign in"),
        (
            _break_sleep,
            "sleeps on power (sleep=1, disksleep=10)",
            "sudo pmset -c sleep 0 disksleep 0",
        ),
        (_break_disk, "only 1 GB free", "docker system prune"),
        (_break_tailscale, "Tailscale is not connected", "tailscale up"),
        (_break_funnel, "no Funnel to the gateway on 127.0.0.1:8080", "scripts/funnel.sh on"),
        (_break_stack, "does not answer", "scripts/mac-prod.sh up"),
        (_break_agent_missing, "is not installed", "scripts/mac-prod.sh install-agent"),
        (_break_agent_unloaded, "installed but not loaded", "scripts/mac-prod.sh install-agent"),
    ],
)
def test_doctor_reports_each_failure_with_a_fix(
    mac: Mac, breaker: object, problem: str, fix: str
) -> None:
    assert callable(breaker)
    breaker(mac)
    result = mac.run(MAC_PROD, "doctor")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("FAIL") == 1, result.stdout
    fail_line = next(line for line in result.stdout.splitlines() if "FAIL" in line)
    assert problem in fail_line
    fix_index = result.stdout.splitlines().index(fail_line) + 1
    assert fix in result.stdout.splitlines()[fix_index]
    assert "doctor: 1 failed" in result.stdout


def test_doctor_skips_the_funnel_check_while_tailscale_is_down(mac: Mac) -> None:
    _break_tailscale(mac)
    result = mac.run(MAC_PROD, "doctor")
    assert "Funnel" not in result.stdout


def test_doctor_warns_without_failing_when_no_backup(mac: Mac) -> None:
    shutil.rmtree(mac.backup_dir)
    result = mac.run(MAC_PROD, "doctor")
    assert result.returncode == 0, result.stdout
    assert "WARN  no backup in" in result.stdout
    assert "doctor: OK (1 warnings)" in result.stdout


def test_doctor_warns_when_the_newest_backup_is_old(mac: Mac) -> None:
    stale = time.time() - 40 * 3600
    for path in mac.backup_dir.iterdir():
        os.utime(path, (stale, stale))
    result = mac.run(MAC_PROD, "doctor")
    assert "WARN  newest backup trainsync-20261017-030000.dump.age is older than 36 h" in (
        result.stdout
    )


def test_doctor_names_the_newest_backup(mac: Mac) -> None:
    _write(mac.backup_dir / "trainsync-20261018-030000.dump.age", "x")
    result = mac.run(MAC_PROD, "doctor")
    assert "ok    last backup trainsync-20261018-030000.dump.age" in result.stdout


def test_doctor_warns_about_filevault_and_missing_auto_login(mac: Mac) -> None:
    mac.stub("fdesetup", "echo 'FileVault is On.'")
    assert "fdesetup authrestart" in mac.run(MAC_PROD, "doctor").stdout
    mac.stub("fdesetup", "echo 'FileVault is Off.'")
    mac.stub("defaults", "exit 1")
    assert "Automatically log in as" in mac.run(MAC_PROD, "doctor").stdout


def test_up_runs_migrations_then_the_stack_with_the_env_file_tag(mac: Mac) -> None:
    result = mac.run(MAC_PROD, "up")
    assert result.returncode == 0, result.stderr
    compose_calls = [line for line in mac.call_lines() if line.startswith("docker compose")]
    prefix = f"docker compose --env-file {mac.env_file} -f {ROOT / 'compose.prod.yml'}"
    assert compose_calls == [
        f"{prefix} --profile migrate run --rm migrate",
        f"{prefix} up -d",
    ]
    assert "TAG=abc123" in mac.call_lines()


def test_up_falls_back_to_the_git_sha_when_the_tag_is_empty(mac: Mac) -> None:
    _write(mac.env_file, 'TRAINSYNC_TAG=""\n')
    result = mac.run(MAC_PROD, "up")
    assert result.returncode == 0, result.stderr
    assert "TAG=deadbeef1234" in mac.call_lines()


def test_up_refuses_without_an_env_file(mac: Mac) -> None:
    mac.env_file.unlink()
    result = mac.run(MAC_PROD, "up")
    assert result.returncode == 1
    assert "cp .env.prod.example .env.prod" in result.stderr
    assert not any(line.startswith("docker compose") for line in mac.call_lines())


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("build",), "build"),
        (("down",), "down"),
        (("status",), "ps"),
        (("logs", "api"), "logs -f --tail=200 api"),
        (("restart",), "restart"),
        (("restart", "worker"), "restart worker"),
    ],
)
def test_compose_commands(mac: Mac, args: tuple[str, ...], expected: str) -> None:
    result = mac.run(MAC_PROD, *args)
    assert result.returncode == 0, result.stderr
    assert mac.call_lines()[-2].endswith(f"compose.prod.yml {expected}")


def test_unknown_command_prints_usage(mac: Mac) -> None:
    result = mac.run(MAC_PROD, "frobnicate")
    assert result.returncode == 2
    assert "install-agent" in result.stderr


def test_install_agent_renders_absolute_paths_and_loads_it(mac: Mac) -> None:
    (mac.home / "Library/LaunchAgents/com.trainsync.stack.plist").unlink()
    result = mac.run(MAC_PROD, "install-agent")
    assert result.returncode == 0, result.stderr
    installed = mac.home / "Library/LaunchAgents/com.trainsync.stack.plist"
    agent = plistlib.loads(installed.read_bytes())
    assert agent["Label"] == "com.trainsync.stack"
    assert agent["RunAtLoad"] is True
    assert agent["ProgramArguments"] == ["/bin/bash", str(START_STACK)]
    assert agent["WorkingDirectory"] == str(ROOT)
    assert agent["StandardOutPath"] == str(mac.home / "Library/Logs/trainsync/stack.log")
    assert (mac.home / "Library/Logs/trainsync").is_dir()
    uid = os.getuid()
    assert f"launchctl bootstrap gui/{uid} {installed}" in mac.call_lines()


def test_uninstall_agent_unloads_and_removes_it(mac: Mac) -> None:
    result = mac.run(MAC_PROD, "uninstall-agent")
    assert result.returncode == 0, result.stderr
    assert not (mac.home / "Library/LaunchAgents/com.trainsync.stack.plist").exists()
    assert f"launchctl bootout gui/{os.getuid()}/com.trainsync.stack" in mac.call_lines()


def test_plist_template_is_valid_and_has_placeholders_only_for_paths() -> None:
    agent = plistlib.loads(TEMPLATE.read_bytes())
    assert agent["ProgramArguments"][1] == "__ROOT__/deploy/macos/start-stack.sh"
    assert agent["StandardErrorPath"] == "__LOG_DIR__/stack.log"


def test_start_stack_waits_for_docker_then_starts_the_stack(mac: Mac) -> None:
    counter = mac.tmp / "docker-info-count"
    mac.stub(
        "docker",
        'if [ "$1" = info ]; then\n'
        f'  n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "{counter}"\n'
        '  [ "$n" -ge 3 ]; exit $?\n'
        "fi",
    )
    result = mac.run(START_STACK, DOCKER_POLL_SECONDS="5")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Docker is up after 10s" in result.stdout
    assert "stack started" in result.stdout
    assert mac.call_lines().count("sleep 5") == 2
    assert any(line.endswith("compose.prod.yml up -d") for line in mac.call_lines())


def test_start_stack_gives_up_after_the_wait(mac: Mac) -> None:
    mac.stub("docker", "exit 1")
    result = mac.run(START_STACK, DOCKER_WAIT_SECONDS="20", DOCKER_POLL_SECONDS="5")
    assert result.returncode == 1
    assert "did not come up within 20s" in result.stdout
    assert mac.call_lines().count("sleep 5") == 4
