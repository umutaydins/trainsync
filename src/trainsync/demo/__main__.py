"""Demo commands (P7.9, ADR 0028).

    python -m trainsync.demo reset          wipe the database and seed it again (DEMO_MODE only)
    python -m trainsync.demo exec CMD ...   run CMD with per-process random signing/encryption keys

`exec` is how compose.demo.yml starts the API and the worker: the demo stores no tokens and
signs no OAuth state (both are refused in demo mode), so a fresh random key per process start is
enough, and no key-shaped string has to live in the repository or in `.env.demo`.
"""

import argparse
import asyncio
import os
import secrets
import sys

from cryptography.fernet import Fernet

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


def generated_keys() -> dict[str, str]:
    return {
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "STATE_SIGNING_KEY": secrets.token_urlsafe(32),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m trainsync.demo", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("reset", help="wipe and re-seed the demo database")
    run = commands.add_parser("exec", help="run a command with generated demo keys")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "exec":
        if not args.argv:
            parser.error("exec needs a command")
        os.execvpe(args.argv[0], args.argv, {**os.environ, **generated_keys()})  # noqa: S606
        return 0  # not reached: exec replaced this process
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
