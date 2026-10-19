"""Repository checks that run in CI with the unit tests: every tracked shell script is
executable in git (a script committed as 100644 breaks `make deploy` and the LaunchAgent on a
fresh clone), and every workflow runs on a pinned runner image."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GIT = shutil.which("git")


@pytest.mark.skipif(GIT is None or not (ROOT / ".git").exists(), reason="needs a git checkout")
def test_every_tracked_shell_script_is_executable() -> None:
    listing = subprocess.run(  # noqa: S603  (fixed arguments)
        [str(GIT), "ls-files", "-s", "--", "*.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert listing, "no shell scripts tracked?"
    wrong = [line.split("\t")[1] for line in listing if not line.startswith("100755 ")]
    assert not wrong, f"not 100755 in git, fix with `git update-index --chmod=+x`: {wrong}"


def test_workflows_run_on_a_pinned_ubuntu() -> None:
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        runners = re.findall(r"runs-on:\s*(\S+)", workflow.read_text(encoding="utf-8"))
        assert runners, workflow.name
        assert set(runners) == {"ubuntu-24.04"}, (workflow.name, runners)
