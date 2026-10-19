"""Password hashing (argon2id) and one-time secret tokens (ADR 0034).

Tokens (sessions, invites, resets) are 32 random bytes, URL-safe; only their SHA-256 is stored,
so a database dump does not hand out working tokens. Hashing a password takes tens of
milliseconds and a lot of memory on purpose: it runs in a worker thread, off the event loop.
"""

import hashlib
import secrets

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

TOKEN_BYTES = 32
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128
# Not an argon2 hash, so no password ever matches: the owner created by the migration has it
# until `scripts/owner.py set-password`.
UNUSABLE_HASH = "!unusable"

_hasher = PasswordHasher()  # argon2id, RFC 9106 low-memory parameters
# Checked against when an email is unknown, so a login takes as long either way.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hasher.hash, password)


async def verify_password(password: str, stored: str | None) -> bool:
    """Constant-ish time: an unknown user (None) or an unusable hash still runs one argon2 check."""
    usable = stored is not None and stored != UNUSABLE_HASH
    target = stored if usable and stored is not None else _DUMMY_HASH

    def check() -> bool:
        try:
            return _hasher.verify(target, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    matched = await anyio.to_thread.run_sync(check)
    return matched and usable


def password_problem(password: str) -> str | None:
    """Why a new password is refused, or None (length only, NIST SP 800-63B)."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"password must be at least {PASSWORD_MIN_LENGTH} characters"
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"password must be at most {PASSWORD_MAX_LENGTH} characters"
    return None


def normal_email(email: str) -> str:
    return email.strip().lower()
