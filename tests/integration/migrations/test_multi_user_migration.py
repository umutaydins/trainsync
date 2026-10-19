"""P8.2, ADR 0035: the single-user database becomes the owner's (migrations 0015-0017).

Seeded at revision 0014 like the real single-user database, then upgraded: every row is the
owner's, the bootstrap chat is linked and its settings kept; downgrading restores the single-user
schema with the data, and upgrading again gives the same result.
"""

import asyncio

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.support.containers import alembic_config

OWNER = "Owner@Example.com"
CHAT = 42
SEED = [
    "INSERT INTO athletes (id, strava_athlete_id) VALUES (1, 1001)",
    "INSERT INTO oauth_tokens (athlete_id, access_token_enc, refresh_token_enc, expires_at, scope)"
    " VALUES (1, 'a', 'r', now(), 'read')",
    "INSERT INTO activities (strava_activity_id, athlete_id, name, sport_type, start_date,"
    " distance_m, moving_time_s, elapsed_time_s, elevation_gain_m, raw)"
    " VALUES (7, 1, 'Run', 'Run', now(), 5000, 1500, 1600, 10, '{}')",
    "INSERT INTO sync_runs (athlete_id, kind, status) VALUES (1, 'backfill', 'succeeded')",
    "INSERT INTO exercises (slug, name, primary_muscle, equipment, is_custom)"
    " VALUES ('my-press', 'My press', 'chest', 'dumbbell', true)",
    "INSERT INTO programs (id, name, goal, days_per_week, weeks, active)"
    " VALUES (1, 'Plan', 'strength', 1, 4, true)",
    "INSERT INTO program_days (id, program_id, day_index, name) VALUES (1, 1, 0, 'Day 1')",
    "INSERT INTO program_exercises (program_day_id, exercise_id, position, sets, rep_min,"
    " rep_max, rest_seconds) SELECT 1, id, 0, 3, 5, 5, 90 FROM exercises WHERE slug = 'my-press'",
    "INSERT INTO workouts (id, client_id, started_at) VALUES (1, gen_random_uuid(), now())",
    "INSERT INTO workout_sets (client_id, workout_id, exercise_id, set_index, reps, weight_kg,"
    " completed_at) SELECT gen_random_uuid(), 1, id, 0, 5, 80, now() FROM exercises"
    " WHERE slug = 'my-press'",
    "INSERT INTO body_metrics (date, weight_kg) VALUES ('2026-10-18', 80)",
    "INSERT INTO daily_checkins (date, status) VALUES ('2026-10-18', 'rest')",
    "INSERT INTO foods (id, name, kcal_100g, source, favorite)"
    " VALUES (1, 'Oats', 380, 'manual', true)",
    "INSERT INTO foods (id, name, kcal_100g, source, barcode)"
    " VALUES (2, 'Cola', 42, 'openfoodfacts', '5449000000996')",
    "INSERT INTO food_logs (client_id, date, meal, food_id, grams, kcal_100g)"
    " VALUES (gen_random_uuid(), '2026-10-18', 'lunch', 1, 50, 380)",
    "INSERT INTO nutrition_profile (id, sex, birth_year, height_cm, activity_baseline)"
    " VALUES (1, 'male', 1990, 180, 'light')",
    "INSERT INTO notifications (kind, object_id) VALUES ('new_activity', 7)",
    "INSERT INTO chat_settings (chat_id, lang, profanity) VALUES (42, 'tr', 'max')",
]
OWNED = (
    "athletes",
    "oauth_tokens",
    "activities",
    "sync_runs",
    "programs",
    "program_days",
    "program_exercises",
    "workouts",
    "workout_sets",
    "body_metrics",
    "daily_checkins",
    "food_logs",
    "nutrition_profile",
    "notifications",
)


async def _run(url: str, *statements: str) -> list[list[tuple[object, ...]]]:
    engine = create_async_engine(url, poolclass=NullPool)
    results = []
    try:
        async with engine.begin() as conn:
            for statement in statements:
                result = await conn.execute(text(statement))
                results.append([tuple(r) for r in result.all()] if result.returns_rows else [])
    finally:
        await engine.dispose()
    return results


def run(url: str, *statements: str) -> list[list[tuple[object, ...]]]:
    return asyncio.run(_run(url, *statements))


@pytest.fixture
def at_0014(pg_url: str) -> object:
    config = alembic_config(pg_url)
    command.downgrade(config, "0014")
    run(pg_url, *SEED)
    yield config
    command.upgrade(config, "head")


def _assert_owned(pg_url: str) -> None:
    [[(owner, email, password)]] = run(
        pg_url, "SELECT id, email, password_hash FROM users WHERE role = 'owner'"
    )
    assert (email, password) == ("owner@example.com", "!unusable")
    for table in OWNED:
        [[(total, mine)]] = run(
            pg_url,
            f"SELECT count(*), count(*) FILTER (WHERE user_id = {owner}) FROM {table}",  # noqa: S608
        )
        assert total == mine > 0, table
    assert run(pg_url, "SELECT id, user_id FROM foods ORDER BY id") == [[(1, owner), (2, None)]]
    assert run(pg_url, "SELECT user_id FROM exercises WHERE is_custom") == [[(owner,)]]
    assert (
        run(pg_url, "SELECT count(*) FROM exercises WHERE NOT is_custom AND user_id IS NULL")[0][0][
            0
        ]
        > 0
    )  # the library stays shared
    assert run(pg_url, "SELECT user_id, food_id FROM food_favorites") == [[(owner, 1)]]
    assert run(pg_url, "SELECT chat_id, user_id FROM telegram_chats") == [[(CHAT, owner)]]
    assert run(pg_url, "SELECT lang, profanity FROM user_settings") == [[("tr", "max")]]


def test_single_user_data_becomes_the_owner_s_and_back(
    pg_url: str, at_0014: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = at_0014
    monkeypatch.setenv("OWNER_EMAIL", OWNER)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", f"{CHAT},43")
    command.upgrade(config, "head")  # type: ignore[arg-type]
    _assert_owned(pg_url)

    command.downgrade(config, "0014")  # type: ignore[arg-type]
    assert run(pg_url, "SELECT id, favorite FROM foods ORDER BY id") == [[(1, True), (2, False)]]
    assert run(pg_url, "SELECT id FROM nutrition_profile") == [[(1,)]]
    assert run(pg_url, "SELECT chat_id, lang, profanity FROM chat_settings") == [
        [(CHAT, "tr", "max")]
    ]
    for table in OWNED:
        [[(count,)]] = run(pg_url, f"SELECT count(*) FROM {table}")  # noqa: S608
        assert count > 0, table

    command.upgrade(config, "head")  # type: ignore[arg-type]  # again: the same result
    _assert_owned(pg_url)


def test_existing_data_needs_owner_email(at_0014: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OWNER_EMAIL", raising=False)
    with pytest.raises(RuntimeError, match="OWNER_EMAIL"):
        command.upgrade(at_0014, "0016")  # type: ignore[arg-type]
    monkeypatch.setenv("OWNER_EMAIL", OWNER)


def test_downgrade_refuses_to_merge_two_users_data(
    pg_url: str, at_0014: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OWNER_EMAIL", OWNER)
    command.upgrade(at_0014, "head")  # type: ignore[arg-type]
    run(
        pg_url,
        "INSERT INTO users (id, email, password_hash, display_name, timezone)"
        " VALUES (99, 'b@example.com', '!', 'B', 'UTC')",
        "INSERT INTO daily_checkins (user_id, date, status) VALUES (99, '2026-10-18', 'done')",
    )
    with pytest.raises(RuntimeError, match="more than one user"):
        command.downgrade(at_0014, "0015")  # type: ignore[arg-type]
