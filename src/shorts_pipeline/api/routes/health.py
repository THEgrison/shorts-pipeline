"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from shorts_pipeline import __version__
from shorts_pipeline.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    dry_run: bool
    env: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — does not check DB/Redis yet (Phase 2)."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        dry_run=settings.dry_run,
        env=settings.app_env,
    )
