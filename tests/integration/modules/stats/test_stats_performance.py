"""P8.10: three years of one user's data; the summary answers in under 300 ms, uncached.

The data is written with set-based SQL (seconds, not minutes): ~5 activities and 3 workouts of
15 sets a week, four meals, a weigh-in and a check-in every day.
"""

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.accounts import create_user, signed_in
from tests.support.factories import create_athlete
from trainsync.core.settings import Settings
from trainsync.entrypoints.api.app import create_app

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
BUDGET_S = 0.300
DAYS = 3 * 365
SEED = """
INSERT INTO activities (user_id, strava_activity_id, athlete_id, name, sport_type, start_date,
                        distance_m, moving_time_s, elapsed_time_s, elevation_gain_m,
                        average_heartrate, raw)
SELECT :u, 900000 + g, :a, 'Run ' || g, CASE WHEN g % 5 = 0 THEN 'Ride' ELSE 'Run' END,
       CAST(:now AS timestamptz) - (g * interval '1 day') * 7 / 5, 5000 + g % 4000,
       1500 + g % 900, 1600, 30, 140 + g % 20, '{}'::jsonb
FROM generate_series(1, CAST(:days AS int) * 5 / 7) AS g;
INSERT INTO workouts (user_id, client_id, started_at, ended_at)
SELECT :u, gen_random_uuid(), CAST(:now AS timestamptz) - (g * interval '1 day') * 7 / 3,
       CAST(:now AS timestamptz) - (g * interval '1 day') * 7 / 3 + interval '1 hour'
FROM generate_series(1, CAST(:days AS int) * 3 / 7) AS g;
INSERT INTO workout_sets (user_id, client_id, workout_id, exercise_id, set_index, reps,
                          weight_kg, is_warmup, completed_at)
SELECT :u, gen_random_uuid(), w.id, e.id, s, 3 + (s + w.id) % 10, 40 + (w.id % 60) + s,
       s = 0, w.started_at + s * interval '3 minutes'
FROM workouts AS w
CROSS JOIN generate_series(0, 14) AS s
JOIN LATERAL (
    SELECT id FROM exercises WHERE user_id IS NULL ORDER BY id OFFSET (s % 5) LIMIT 1
) AS e ON true
WHERE w.user_id = :u;
INSERT INTO foods (user_id, name, kcal_100g, food_group) VALUES (:u, 'Perf food', 250, 'sweets');
INSERT INTO food_logs (user_id, client_id, date, meal, food_id, grams, kcal_100g, protein_100g,
                       carbs_100g, fat_100g, sugars_100g, food_group)
SELECT :u, gen_random_uuid(), CAST(CAST(:now AS timestamptz) AS date) - g, m,
       (SELECT id FROM foods WHERE user_id = :u), 200, 250, 10, 30, 8, 5 + g % 20, 'sweets'
FROM generate_series(0, CAST(:days AS int)) AS g
CROSS JOIN unnest(ARRAY['breakfast', 'lunch', 'dinner', 'snack']) AS m;
INSERT INTO body_metrics (user_id, date, weight_kg)
SELECT :u, CAST(CAST(:now AS timestamptz) AS date) - g, 85 - g * 0.004
FROM generate_series(0, CAST(:days AS int)) AS g;
INSERT INTO daily_checkins (user_id, date, status)
SELECT :u, CAST(CAST(:now AS timestamptz) AS date) - g,
       CASE WHEN g % 9 = 0 THEN 'rest' ELSE 'done' END
FROM generate_series(1, CAST(:days AS int)) AS g;
"""


@pytest.fixture
async def app(integration_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(integration_settings)
    app.state.clock = lambda: NOW
    async with LifespanManager(app):
        yield app


async def test_three_years_summarise_within_budget(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(sessionmaker, "heavy@example.com", timezone="Europe/Berlin")
    athlete = await create_athlete(sessionmaker, 6001, user_id=user.id)
    async with sessionmaker.begin() as session:
        for statement in filter(str.strip, SEED.split(";")):
            await session.execute(
                text(statement), {"u": user.id, "a": athlete, "now": NOW, "days": DAYS}
            )
        await session.execute(text("ANALYZE"))
    async with signed_in(app, user) as api:
        assert (await api.get("/v1/me")).status_code == 200  # warm the pool
        timings = {}
        for period in ("all", "year", "12m", "month"):
            started = time.perf_counter()
            response = await api.get("/v1/stats/summary", params={"period": period})
            timings[period] = time.perf_counter() - started
            assert response.status_code == 200, response.text
        body = response.json()
    assert body["strength"]["sessions"]["value"] > 0
    assert all(t < BUDGET_S for t in timings.values()), timings
