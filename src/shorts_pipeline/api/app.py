"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from shorts_pipeline import __version__
from shorts_pipeline.api.routes import dashboard, health, metrics_route, pipeline
from shorts_pipeline.config import get_settings
from shorts_pipeline.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_logs=settings.log_json)
    logger.info(
        "api.startup",
        version=__version__,
        dry_run=settings.dry_run,
        env=settings.app_env,
    )
    yield
    logger.info("api.shutdown")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(metrics_route.router)
    app.include_router(pipeline.router)
    app.include_router(dashboard.router)

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=302)

    return app


# ASGI entrypoint for uvicorn: `shorts_pipeline.api.app:app`
app = create_app()
