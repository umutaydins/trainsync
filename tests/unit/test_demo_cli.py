"""`python -m trainsync.demo exec`: the demo's keys are generated per process, never stored."""

import pytest
from cryptography.fernet import Fernet

from trainsync.demo import __main__ as cli


class ExecCalledError(Exception):
    def __init__(self, file: str, argv: list[str], env: dict[str, str]) -> None:
        self.file, self.argv, self.env = file, argv, env


def _fake_exec(file: str, argv: list[str], env: dict[str, str]) -> None:
    raise ExecCalledError(file, argv, env)  # like the real one, it never returns


def _run(argv: list[str]) -> ExecCalledError:
    with pytest.raises(ExecCalledError) as info:
        cli.main(argv)
    return info.value


def test_exec_runs_the_command_with_fresh_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.os, "execvpe", _fake_exec)
    monkeypatch.setenv("DEMO_MODE", "true")

    first = _run(["exec", "uvicorn", "--port", "8000"])
    second = _run(["exec", "uvicorn", "--port", "8000"])

    assert (first.file, first.argv) == ("uvicorn", ["uvicorn", "--port", "8000"])
    assert first.env["DEMO_MODE"] == "true"
    Fernet(first.env["TOKEN_ENCRYPTION_KEY"])  # a valid key
    assert len(first.env["STATE_SIGNING_KEY"]) >= 32
    assert first.env["TOKEN_ENCRYPTION_KEY"] != second.env["TOKEN_ENCRYPTION_KEY"]


def test_exec_needs_a_command() -> None:
    with pytest.raises(SystemExit):
        cli.main(["exec"])
