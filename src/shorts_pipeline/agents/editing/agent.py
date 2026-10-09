"""Editing Agent: cut, reframe 9:16, captions, export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from shorts_pipeline.agents.base import Agent, AgentInput, AgentOutput
from shorts_pipeline.agents.editing.renderer import RenderRequest, render_short
from shorts_pipeline.agents.editing.styles import StyleConfig, load_style_template
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.db.enums import AgentName
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.storage.base import StorageBackend

logger = get_logger(__name__)


class EditingInput(AgentInput):
    clip_id: int
    source_video_path: Path
    start_sec: float
    end_sec: float
    words: list[dict[str, Any]] = Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    style_name: str | None = None
    work_dir: Path | None = None
    background_music: Path | None = None


class EditingOutput(AgentOutput):
    clip_id: int
    storage_key: str | None = None
    thumbnail_key: str | None = None
    subtitle_key: str | None = None
    duration_sec: float | None = None
    width: int = 1080
    height: int = 1920
    file_size_bytes: int | None = None
    reframe_mode: str | None = None
    style_template_name: str | None = None
    title: str | None = None
    description: str | None = None


class EditingAgent(Agent[EditingInput, EditingOutput]):
    name = AgentName.EDITING

    def __init__(
        self,
        *,
        storage: StorageBackend | None = None,
        settings: Settings | None = None,
        styles_dir: Path | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings or get_settings()
        self.styles_dir = styles_dir

    def run(self, input_data: EditingInput) -> EditingOutput:
        style_name = input_data.style_name or self.settings.editing_default_style_template
        style_data = load_style_template(style_name, styles_dir=self.styles_dir)
        style: StyleConfig = style_data.config

        work = input_data.work_dir or (
            self.settings.storage_temp_dir / f"edit_clip_{input_data.clip_id}"
        )
        work.mkdir(parents=True, exist_ok=True)
        out_path = work / f"clip_{input_data.clip_id}_short.mp4"
        sub_path = work / f"clip_{input_data.clip_id}.ass"
        thumb_path = work / f"clip_{input_data.clip_id}.jpg"

        result = render_short(
            RenderRequest(
                source_video=input_data.source_video_path,
                output_video=out_path,
                start_sec=input_data.start_sec,
                end_sec=input_data.end_sec,
                words=input_data.words,
                style=style,
                subtitle_path=sub_path,
                thumbnail_path=thumb_path,
                background_music=input_data.background_music,
            ),
            settings=self.settings,
        )

        storage_key = thumbnail_key = subtitle_key = None
        if self.storage is not None:
            storage_key = self.storage.put_file(
                f"renders/clip_{input_data.clip_id}/final.mp4",
                result.output_video,
            )
            if result.thumbnail_path.exists() and result.thumbnail_path.stat().st_size > 0:
                thumbnail_key = self.storage.put_file(
                    f"renders/clip_{input_data.clip_id}/thumb.jpg",
                    result.thumbnail_path,
                )
            subtitle_key = self.storage.put_file(
                f"renders/clip_{input_data.clip_id}/captions.ass",
                result.subtitle_path,
            )

        logger.info(
            "editing.completed",
            clip_id=input_data.clip_id,
            reframe=result.reframe_mode,
            size=result.file_size_bytes,
        )
        return EditingOutput(
            success=True,
            message="Render completed",
            clip_id=input_data.clip_id,
            storage_key=storage_key or str(result.output_video),
            thumbnail_key=thumbnail_key,
            subtitle_key=subtitle_key,
            duration_sec=result.duration_sec,
            width=result.width,
            height=result.height,
            file_size_bytes=result.file_size_bytes,
            reframe_mode=result.reframe_mode,
            style_template_name=style_name,
            title=input_data.title,
            description=input_data.description,
        )
