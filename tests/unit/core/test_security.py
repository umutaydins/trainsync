"""ADR 0034: argon2id hashes, hashed tokens and the password policy."""

from trainsync.core.security import (
    UNUSABLE_HASH,
    hash_password,
    new_token,
    normal_email,
    password_problem,
    token_hash,
    verify_password,
)


async def test_hash_and_verify() -> None:
    stored = await hash_password("correct horse battery")
    assert stored.startswith("$argon2id$")
    assert await verify_password("correct horse battery", stored)
    assert not await verify_password("wrong", stored)
    assert not await verify_password("anything", UNUSABLE_HASH)
    assert not await verify_password("anything", None)
    assert not await verify_password("anything", "not-a-hash")


def test_tokens_are_random_and_only_their_digest_is_kept() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 43
    assert token_hash(first) == token_hash(first)
    assert len(token_hash(first)) == 32


def test_password_policy_is_length_only() -> None:
    assert password_problem("short") is not None
    assert password_problem("x" * 129) is not None
    assert password_problem("ten chars!") is None
    assert normal_email("  Some.One@Example.COM ") == "some.one@example.com"
