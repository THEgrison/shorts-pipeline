"""Editing Agent tests — ASS generation + real ffmpeg on fixture."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from shorts_pipeline.agents.editing.agent import EditingAgent, EditingInput
from shorts_pipeline.agents.editing.reframe import build_reframe_filter
from shorts_pipeline.agents.editing.styles import StyleConfig, load_style_template
from shorts_pipeline.agents.editing.subtitles import generate_ass
from shorts_pipeline.config import Settings
from shorts_pipeline.db.enums import ClipStatus, LicenseBasis, VideoStatus
from shorts_pipeline.db.models import Clip, Render, SourceVideo
from shorts_pipeline.orchestrator.service import Orchestrator
from shorts_pipeline.storage.local import LocalStorageBackend

FIXTURE = Path(__file__).parent / "fixtures" / "sample_landscape.mp4"


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample fixture missing")
def test_generate_ass_highlight() -> None:
    words = [
        {"word": "Bonjour", "start": 1.0, "end": 1.3},
        {"word": "tout", "start": 1.3, "end": 1.5},
        {"word": "le", "start": 1.5, "end": 1.6},
        {"word": "monde", "start": 1.6, "end": 2.0},
    ]
    ass = generate_ass(words, style=StyleConfig(), clip_start=1.0, clip_end=5.0)
    assert "Dialogue:" in ass
    assert (
        "FFE566" in ass.upper()
        or "66E5FF" in ass.upper()
        or "highlight" in ass.lower()
        or "&H" in ass
    )
    assert "Bonjour" in ass


def test_reframe_blur_fallback() -> None:
    plan = build_reframe_filter(width=1080, height=1920)
    assert plan.mode == "blur_center"
    assert "boxblur" in plan.filter_complex


def test_reframe_face_crop() -> None:
    plan = build_reframe_filter(
        width=1080,
        height=1920,
        face_center_x=0.5,
        source_width=1280,
        source_height=720,
    )
    assert plan.mode == "face_crop"
    assert "crop=" in plan.filter_complex


def test_load_style_template() -> None:
    tmpl = load_style_template("tiktok_default")
    assert tmpl.name == "tiktok_default"
    assert tmpl.config.font_size >= 48


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample fixture missing")
def test_editing_agent_ffmpeg_render(settings: Settings, tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "store")
    agent = EditingAgent(
        storage=storage,
        settings=settings,
        styles_dir=Path("config/styles"),
    )
    words = [
        {"word": "Hello", "start": 1.0, "end": 1.4},
        {"word": "world", "start": 1.4, "end": 2.0},
        {"word": "this", "start": 2.0, "end": 2.3},
        {"word": "is", "start": 2.3, "end": 2.5},
        {"word": "a", "start": 2.5, "end": 2.6},
        {"word": "test", "start": 2.6, "end": 3.2},
    ]
    # Clamp clip to fixture length (8s); min analysis duration ignored for editing unit test
    result = agent.run(
        EditingInput(
            clip_id=42,
            source_video_path=FIXTURE,
            start_sec=1.0,
            end_sec=5.0,
            words=words,
            title="Test short",
            description="Fixture render",
            work_dir=tmp_path / "work",
            dry_run=True,
        )
    )
    assert result.success
    assert result.storage_key
    assert result.duration_sec == pytest.approx(4.0)
    assert result.width == settings.editing_width
    assert result.height == settings.editing_height
    assert result.file_size_bytes and result.file_size_bytes > 1000
    # Stored file exists
    assert storage.exists(result.storage_key)
    if result.subtitle_key:
        ass_text = Path(storage.url_or_path(result.subtitle_key)).read_text(encoding="utf-8")
        assert "Dialogue:" in ass_text


@pytest.mark.skipif(not FIXTURE.exists(), reason="sample fixture missing")
def test_orchestrator_editing_with_fixture(
    sync_session: Session, settings: Settings, tmp_path: Path
) -> None:
    video = SourceVideo(
        youtube_video_id="edit_fix",
        youtube_channel_id="UCcc",
        title="Edit me",
        license="creativeCommon",
        license_basis=LicenseBasis.CREATIVE_COMMONS,
        status=VideoStatus.ANALYZED,
        storage_key=str(FIXTURE),
        duration_sec=8,
    )
    sync_session.add(video)
    sync_session.flush()
    clip = Clip(
        source_video_id=video.id,
        start_sec=1.0,
        end_sec=5.0,
        score=90,
        hook="Hello",
        suggested_title="Fixture short",
        status=ClipStatus.ANALYZED,
        rank=1,
    )
    sync_session.add(clip)
    sync_session.commit()

    agent = EditingAgent(storage=LocalStorageBackend(tmp_path), settings=settings)
    orch = Orchestrator(sync_session, settings=settings, editing_agent=agent)
    out = orch.run_editing(clip.id)
    assert out["success"]
    assert out["clip_status"] in {
        ClipStatus.AWAITING_REVIEW.value,
        ClipStatus.APPROVED.value,
    }
    render = sync_session.get(Render, out["render_id"])
    assert render is not None
    assert render.storage_key
