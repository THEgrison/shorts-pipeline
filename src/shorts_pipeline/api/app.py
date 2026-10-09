"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from shorts_pipeline import __version__
from shorts_pipeline.api.routes import health, metrics_route, pipeline
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

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_home() -> str:
        """Minimal control dashboard placeholder (Phase 7 expands this)."""
        dry = "on" if settings.dry_run else "off"
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <title>{settings.app_name}</title>
  <style>
    :root {{ --bg:#0f1419; --fg:#e7ecf1; --accent:#3dd6c6; }}
    body {{ font-family: "IBM Plex Sans", system-ui, sans-serif; background:var(--bg);
           color:var(--fg); margin:0; padding:2rem; }}
    h1 {{ color:var(--accent); }}
    code {{ background:#1c2430; padding:.2rem .4rem; border-radius:4px; }}
  </style>
</head>
<body>
  <h1>{settings.app_name}</h1>
  <p>Pipeline multi-agents YouTube → Shorts — v{__version__}</p>
  <p>Mode DRY_RUN: <code>{dry}</code></p>
  <ul>
    <li><a href="/health">/health</a></li>
    <li><a href="/metrics">/metrics</a></li>
    <li><a href="/docs">/docs</a></li>
  </ul>
</body>
</html>"""

    return app


# ASGI entrypoint for uvicorn: `shorts_pipeline.api.app:app`
app = create_app()
