"""`/v1/nutrition/profile`: the BMR inputs, the daily targets and today's BMR estimate."""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from trainsync.core.deps import ClockDep, SessionmakerDep
from trainsync.core.errors import UNAUTHORIZED, error
from trainsync.modules.auth.dependencies import CurrentUser
from trainsync.modules.nutrition.energy import target_warning
from trainsync.modules.nutrition.models import ActivityBaseline, NutritionProfile, Sex
from trainsync.modules.nutrition.repository import NutritionRepository, ProfileValues
from trainsync.modules.nutrition.routes.common import nutrition_router, today
from trainsync.modules.nutrition.schemas import ProfileIn, ProfileOut
from trainsync.modules.nutrition.schemas.common import optional_float
from trainsync.modules.nutrition.summary import estimate_bmr
from trainsync.modules.nutrition.summary import latest_weight as latest_body_weight

router = nutrition_router()


@router.get(
    "/profile",
    summary="Nutrition profile",
    description="Profile, targets and today's BMR estimate.",
    response_model=ProfileOut,
    responses={**UNAUTHORIZED, 404: error("No profile yet", "profile not set")},
)
async def get_profile(
    principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep
) -> ProfileOut:
    async with sessionmaker() as session:
        profile = await NutritionRepository(session, principal.user_id).profile()
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not set")
        return await _profile_out(session, principal.user_id, profile, today(clock))


@router.put(
    "/profile",
    summary="Set the nutrition profile",
    description=(
        "Replaces the profile. A `kcal_target` below the estimated BMR is accepted and comes "
        "back with a `warning`."
    ),
    response_model=ProfileOut,
    responses={**UNAUTHORIZED},
)
async def put_profile(
    principal: CurrentUser, sessionmaker: SessionmakerDep, clock: ClockDep, body: ProfileIn
) -> ProfileOut:
    values = ProfileValues(
        sex=body.sex.value,
        birth_year=body.birth_year,
        height_cm=Decimal(str(body.height_cm)),
        activity_baseline=body.activity_baseline.value,
        kcal_target=body.kcal_target,
        protein_target_g=body.protein_target_g,
    )
    async with sessionmaker.begin() as session:
        profile = await NutritionRepository(session, principal.user_id).put_profile(values, clock())
        return await _profile_out(session, principal.user_id, profile, today(clock))


async def _profile_out(
    session: AsyncSession, user_id: int, profile: NutritionProfile, day: date
) -> ProfileOut:
    weight = await latest_body_weight(session, user_id, day)
    bmr = estimate_bmr(profile, weight, day)
    return ProfileOut(
        sex=Sex(profile.sex),
        birth_year=profile.birth_year,
        height_cm=float(profile.height_cm),
        activity_baseline=ActivityBaseline(profile.activity_baseline),
        kcal_target=profile.kcal_target,
        protein_target_g=profile.protein_target_g,
        bmr_kcal=optional_float(bmr.bmr),
        weight_kg=optional_float(weight.weight_kg) if weight else None,
        weight_date=weight.date if weight else None,
        estimate_unavailable_reason=bmr.gap,
        warning=target_warning(profile.kcal_target, bmr.bmr),
        updated_at=profile.updated_at,
    )
