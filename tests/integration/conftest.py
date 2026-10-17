"""Integration suite: everything under tests/integration runs against testcontainers Postgres
and Redis (fixtures in tests/support/containers.py) and starts from empty tables and Redis."""

from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Everything under tests/integration is an integration test, marked or not."""
    for item in items:
        if _HERE in item.path.parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _clean_state(clean_state: None) -> None:
    """Sync on purpose (see `clean_state`): sync tests that drive Alembic can use it too."""
