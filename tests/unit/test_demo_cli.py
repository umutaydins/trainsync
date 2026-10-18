"""`python -m trainsync.demo exec`: the demo's keys are generated per process, never stored."""

import pytest
from cryptography.fernet import Fernet

from trainsync.demo import __main__ as cli


def test_exec_runs_the_command_with_fresh_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str], dict[str, str]]] = []
    monkeypatch.setattr(cli.os, "execvpe", lambda f, a, e: calls.append((f, a, e)))
    monkeypatch.setenv("DEMO_MODE", "true")

    cli.main(["exec", "uvicorn", "--port", "8000"])
    cli.main(["exec", "uvicorn", "--port", "8000"])

    (file, argv, env), (_, _, env2) = calls
    assert (file, argv) == ("uvicorn", ["uvicorn", "--port", "8000"])
    assert env["DEMO_MODE"] == "true"
    Fernet(env["TOKEN_ENCRYPTION_KEY"])  # a valid key
    assert len(env["STATE_SIGNING_KEY"]) >= 32
    assert env["TOKEN_ENCRYPTION_KEY"] != env2["TOKEN_ENCRYPTION_KEY"]


def test_exec_needs_a_command() -> None:
    with pytest.raises(SystemExit):
        cli.main(["exec"])
