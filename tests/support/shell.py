"""Run the repo's shell scripts against stub commands (P7.2, P7.3, P7.5).

Every external command a script uses (docker, pmset, tailscale, df, curl, launchctl, fdesetup,
defaults, git, open, sleep, gh) is a stub on a temporary PATH, and HOME is a temporary directory, so
nothing touches the machine the tests run on.
"""

import atexit
import functools
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") or "/bin/bash"

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
    "gh",
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
def stub_bin() -> Path:
    bin_dir = Path(tempfile.mkdtemp(prefix="shell-stubs-"))
    atexit.register(shutil.rmtree, bin_dir, True)
    dispatcher = bin_dir / "_stub"
    dispatcher.write_text(DISPATCHER, encoding="utf-8")
    dispatcher.chmod(0o755)
    for name in STUBBED:
        (bin_dir / name).symlink_to(dispatcher)
    return bin_dir


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@dataclass
class Mac:
    """A fake Mac: a temporary HOME, an env file and a stub behavior per command."""

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
            "PATH": f"{stub_bin()}:/usr/bin:/bin",
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
