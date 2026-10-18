"""`python -m trainsync.demo reset`: wipe the demo database and seed it again (DEMO_MODE only)."""

import argparse
import asyncio
import sys

from trainsync.core.clock import utc_now
from trainsync.core.logging import configure_logging
from trainsync.core.settings import Settings, get_settings
from trainsync.db.session import create_engine, create_sessionmaker
from trainsync.demo.store import DemoModeRequiredError, ResetSummary, reset


async def run_reset(settings: Settings) -> ResetSummary:
    engine = create_engine(settings)
    try:
        return await reset(settings, create_sessionmaker(engine), utc_now)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m trainsync.demo", description=__doc__)
    parser.add_argument("command", choices=["reset"])
    parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    try:
        summary = asyncio.run(run_reset(settings))
    except DemoModeRequiredError as exc:
        print(f"trainsync.demo: {exc}", file=sys.stderr)
        return 2
    print(f"demo reset: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
