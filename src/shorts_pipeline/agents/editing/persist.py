"""Persist editing results into renders table."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shorts_pipeline.agents.editing.agent import EditingOutput
from shorts_pipeline.db.enums import RenderStatus
from shorts_pipeline.db.models import Render
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def persist_render(session: Session, result: EditingOutput) -> int:
    """Insert a RENDERED row for the clip. Returns render id."""
    render = Render(
        clip_id=result.clip_id,
        status=RenderStatus.RENDERED,
        storage_key=result.storage_key,
        thumbnail_key=result.thumbnail_key,
        subtitle_key=result.subtitle_key,
        style_template_name=result.style_template_name,
        duration_sec=result.duration_sec,
        width=result.width,
        height=result.height,
        file_size_bytes=result.file_size_bytes,
        title=result.title,
        description=result.description,
    )
    session.add(render)
    session.flush()
    logger.info("editing.render_persisted", render_id=render.id, clip_id=result.clip_id)
    return render.id
