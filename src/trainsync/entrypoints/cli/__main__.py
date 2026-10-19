"""python -m trainsync.entrypoints.cli {invite,owner} …

invite create [--note TEXT]     a single-use invite; prints the code and the register link
invite list                     every invite with its status
invite revoke ID                revoke an unused invite
owner set-password [--stdin]    create the owner from OWNER_EMAIL if missing, set its password
owner reset-link EMAIL          a one-time password reset link for that account
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trainsync.core.clock import utc_now
from trainsync.core.db import create_engine, create_sessionmaker
from trainsync.core.security import normal_email
from trainsync.core.settings import Settings, get_settings
from trainsync.modules.admin.router import invite_status
from trainsync.modules.auth import service
from trainsync.modules.auth.errors import AuthError
from trainsync.modules.auth.links import invite_link, reset_link
from trainsync.modules.auth.repository import InviteRepository, UserRepository

Sessionmaker = async_sessionmaker[AsyncSession]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m trainsync.entrypoints.cli")
    groups = root.add_subparsers(dest="group", required=True)
    invite = groups.add_parser("invite").add_subparsers(dest="command", required=True)
    create = invite.add_parser("create")
    create.add_argument("--note", default=None)
    invite.add_parser("list")
    revoke = invite.add_parser("revoke")
    revoke.add_argument("id", type=int)
    owner = groups.add_parser("owner").add_subparsers(dest="command", required=True)
    set_password = owner.add_parser("set-password")
    set_password.add_argument("--stdin", action="store_true", help="read the password from stdin")
    link = owner.add_parser("reset-link")
    link.add_argument("email")
    return root


async def invite_command(db: Sessionmaker, settings: Settings, args: argparse.Namespace) -> int:
    if args.command == "create":
        async with db() as session:
            owner = await UserRepository(session).owner()
        invite, code = await service.create_invite(
            db, settings, utc_now, created_by=owner.id if owner else None, note=args.note
        )
        print(f"invite {invite.id}, valid until {invite.expires_at:%Y-%m-%d %H:%M} UTC")
        print(f"code: {code}")
        print(f"link: {invite_link(settings, code)}")
        return 0
    if args.command == "list":
        now = utc_now()
        async with db() as session:
            rows = await InviteRepository(session).all()
        for row in rows:
            note = f"  {row.note}" if row.note else ""
            print(f"{row.id:>5}  {invite_status(row, now):<8} {row.expires_at:%Y-%m-%d}{note}")
        return 0
    async with db.begin() as session:
        revoked = await InviteRepository(session).revoke(args.id, utc_now())
    print("revoked" if revoked else "no open invite with that id", file=sys.stderr)
    return 0 if revoked else 1


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("new owner password: ")
    if getpass.getpass("again: ") != first:
        raise SystemExit("the passwords differ")
    return first


async def owner_command(db: Sessionmaker, settings: Settings, args: argparse.Namespace) -> int:
    if args.command == "set-password":
        if not settings.owner_email:
            raise SystemExit("set OWNER_EMAIL first")
        owner = await service.ensure_owner(db, settings, email=settings.owner_email)
        await service.set_password(db, utc_now, owner.id, read_password(args.stdin))
        print(f"password set for {owner.email}; every session of the owner ended")
        return 0
    async with db() as session:
        user = await UserRepository(session).by_email(normal_email(args.email))
    if user is None:
        raise SystemExit("no account with that email")
    token, expires_at = await service.create_reset(db, settings, utc_now, user.id)
    print(f"valid until {expires_at:%Y-%m-%d %H:%M} UTC, once:")
    print(reset_link(settings, token))
    return 0


async def run(argv: Sequence[str]) -> int:
    args = parser().parse_args(argv)
    settings = get_settings()
    engine = create_engine(settings)
    try:
        db = create_sessionmaker(engine)
        if args.group == "invite":
            return await invite_command(db, settings, args)
        return await owner_command(db, settings, args)
    except AuthError as exc:
        raise SystemExit(exc.detail) from None
    finally:
        await engine.dispose()


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
