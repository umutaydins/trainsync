"""Health endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness: the process is up")
async def live() -> dict[str, str]:
    return {"status": "ok"}
