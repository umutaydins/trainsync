"""Rows for the progress statistics tests (P8.10), written straight through the ORM.

`Seeder` keeps one session open, so a test (or three years of performance data) adds many rows
in one transaction and commits once.
"""

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.modules.activities.models import Activity
from trainsync.modules.checkin.models import DailyCheckin
from trainsync.modules.nutrition.models import Food, FoodLog, NutritionProfile
from trainsync.modules.training.models import (
    BodyMetric,
    Exercise,
    Program,
    ProgramDay,
    ProgramExercise,
    Workout,
    WorkoutSet,
)

_ids = itertools.count(700_000)


@dataclass(frozen=True, slots=True)
class Lift:
    """One set: exercise slug, reps, kg; `warmup` sets never count."""

    slug: str
    reps: int
    kg: float
    warmup: bool = False


@dataclass
class Seeder:
    session: AsyncSession
    user_id: int
    athlete_id: int | None = None
    _exercises: dict[str, int] = field(default_factory=dict)
    _foods: dict[tuple[str | None, int | None], int] = field(default_factory=dict)

    async def exercise_id(self, slug: str) -> int:
        if slug not in self._exercises:
            found = await self.session.scalar(
                select(Exercise.id).where(Exercise.slug == slug, Exercise.user_id.is_(None))
            )
            assert found is not None, slug
            self._exercises[slug] = found
        return self._exercises[slug]

    def activity(
        self,
        start: datetime,
        *,
        sport: str = "Run",
        distance_m: float = 5000.0,
        moving_s: int = 1500,
        elevation_m: float = 20.0,
        heartrate: float | None = None,
    ) -> Activity:
        assert self.athlete_id is not None, "Seeder(athlete_id=...) for activities"
        strava_id = next(_ids)
        row = Activity(
            user_id=self.user_id,
            strava_activity_id=strava_id,
            athlete_id=self.athlete_id,
            name=f"{sport} {strava_id}",
            sport_type=sport,
            start_date=start,
            distance_m=distance_m,
            moving_time_s=moving_s,
            elapsed_time_s=moving_s,
            elevation_gain_m=elevation_m,
            average_heartrate=heartrate,
            raw={"id": strava_id},
        )
        self.session.add(row)
        return row

    async def workout(
        self,
        started: datetime,
        lifts: list[Lift],
        *,
        minutes: int = 60,
        program_day_id: int | None = None,
    ) -> Workout:
        workout = Workout(
            user_id=self.user_id,
            client_id=uuid.uuid4(),
            started_at=started,
            ended_at=started + timedelta(minutes=minutes),
            program_day_id=program_day_id,
        )
        self.session.add(workout)
        await self.session.flush()
        for index, lift in enumerate(lifts):
            self.session.add(
                WorkoutSet(
                    user_id=self.user_id,
                    client_id=uuid.uuid4(),
                    workout_id=workout.id,
                    exercise_id=await self.exercise_id(lift.slug),
                    set_index=index,
                    reps=lift.reps,
                    weight_kg=Decimal(str(lift.kg)),
                    is_warmup=lift.warmup,
                    completed_at=started + timedelta(minutes=index + 1),
                )
            )
        return workout

    async def _food(self, group: str | None, nova: int | None) -> int:
        key = (group, nova)
        if key not in self._foods:
            food = Food(
                user_id=self.user_id,
                name=f"food {group} {nova} {next(_ids)}",
                kcal_100g=Decimal(100),
                food_group=group,
                nova_group=nova,
            )
            self.session.add(food)
            await self.session.flush()
            self._foods[key] = food.id
        return self._foods[key]

    async def meal(
        self,
        day: date,
        *,
        kcal_100g: float,
        grams: float = 100,
        protein: float = 0,
        carbs: float = 0,
        fat: float = 0,
        sugars: float = 0,
        group: str | None = None,
        nova: int | None = None,
    ) -> None:
        self.session.add(
            FoodLog(
                user_id=self.user_id,
                client_id=uuid.uuid4(),
                date=day,
                meal="lunch",
                food_id=await self._food(group, nova),
                grams=Decimal(str(grams)),
                kcal_100g=Decimal(str(kcal_100g)),
                protein_100g=Decimal(str(protein)),
                carbs_100g=Decimal(str(carbs)),
                fat_100g=Decimal(str(fat)),
                sugars_100g=Decimal(str(sugars)),
                food_group=group,
                nova_group=nova,
            )
        )

    async def program(
        self, created: datetime, days: list[tuple[int | None, list[tuple[str, int]]]]
    ) -> list[int]:
        """An active program: per day its weekday (or None) and (exercise slug, sets)."""
        program = Program(
            user_id=self.user_id,
            name="Plan",
            goal="strength",
            days_per_week=len(days),
            weeks=8,
            active=True,
            created_at=created,
        )
        self.session.add(program)
        await self.session.flush()
        day_ids: list[int] = []
        for index, (weekday, exercises) in enumerate(days):
            day = ProgramDay(
                user_id=self.user_id,
                program_id=program.id,
                day_index=index,
                name=f"Day {index + 1}",
                weekday=weekday,
            )
            self.session.add(day)
            await self.session.flush()
            day_ids.append(day.id)
            for position, (slug, sets) in enumerate(exercises):
                self.session.add(
                    ProgramExercise(
                        user_id=self.user_id,
                        program_day_id=day.id,
                        exercise_id=await self.exercise_id(slug),
                        position=position,
                        sets=sets,
                        rep_min=5,
                        rep_max=8,
                        rest_seconds=120,
                    )
                )
        return day_ids

    def weight(self, day: date, kg: float) -> None:
        self.session.add(BodyMetric(user_id=self.user_id, date=day, weight_kg=Decimal(str(kg))))

    def checkin(self, day: date, status: str = "done") -> None:
        self.session.add(DailyCheckin(user_id=self.user_id, date=day, status=status))

    def target(self, kcal: int) -> None:
        self.session.add(
            NutritionProfile(
                user_id=self.user_id,
                sex="male",
                birth_year=1990,
                height_cm=Decimal(180),
                activity_baseline="moderate",
                kcal_target=kcal,
            )
        )
