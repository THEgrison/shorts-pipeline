"""Orchestrator + dummy agents end-to-end on SQLite."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.orm import Session

from shorts_pipeline.config import clear_settings_cache, get_settings
from shorts_pipeline.db.enums import AgentName, ClipStatus, PublicationStatus, VideoStatus
from shorts_pipeline.db.models import Clip, Publication, Render, SourceVideo
from shorts_pipeline.orchestrator.pause import (
    clear_local_pauses,
    is_agent_paused,
    pause_agent,
    resume_agent,
)
from shorts_pipeline.orchestrator.service import Orchestrator


@pytest.fixture
def orch(sync_session: Session) -> Orchestrator:
    clear_local_pauses()
    os.environ["REQUIRE_REVIEW"] = "true"
    os.environ["DRY_RUN"] = "true"
    clear_settings_cache()
    return Orchestrator(sync_session, settings=get_settings())


def test_full_dummy_pipeline_with_review(orch: Orchestrator, sync_session: Session) -> None:
    disc = orch.run_discovery(niches=["tech_fr"])
    assert disc["success"] is True
    assert len(disc["created_ids"]) == 1
    video_id = disc["created_ids"][0]

    # Idempotent discovery (no duplicate)
    disc2 = orch.run_discovery(niches=["tech_fr"])
    assert disc2["created_ids"] == []

    analysis = orch.run_analysis(video_id)
    assert analysis["success"] is True
    clip_id = analysis["clip_ids"][0]

    video = sync_session.get(SourceVideo, video_id)
    assert video is not None
    assert video.status == VideoStatus.ANALYZED
    assert video.license_basis.value == "creative_commons"

    # Idempotent analysis
    analysis2 = orch.run_analysis(video_id)
    assert analysis2.get("idempotent") is True

    edit = orch.run_editing(clip_id)
    assert edit["success"] is True
    assert edit["clip_status"] == ClipStatus.AWAITING_REVIEW.value
    render_id = edit["render_id"]

    # Publishing blocked until review
    blocked = orch.run_publishing(render_id)
    assert blocked.get("awaiting_review") is True

    orch.approve_clip(clip_id)
    pub = orch.run_publishing(render_id)
    assert pub["success"] is True
    assert pub["publication_status"] == PublicationStatus.DRY_RUN.value

    clip = sync_session.get(Clip, clip_id)
    assert clip is not None
    assert clip.status == ClipStatus.PUBLISHED
    assert sync_session.query(Render).count() == 1
    assert sync_session.query(Publication).count() == 1

    # Idempotent publish
    pub2 = orch.run_publishing(render_id)
    assert pub2.get("idempotent") is True


def test_pipeline_without_review(sync_session: Session) -> None:
    clear_local_pauses()
    os.environ["REQUIRE_REVIEW"] = "false"
    os.environ["DRY_RUN"] = "true"
    clear_settings_cache()
    orch = Orchestrator(sync_session, settings=get_settings())

    disc = orch.run_discovery()
    video_id = disc["created_ids"][0]
    analysis = orch.run_analysis(video_id)
    clip_id = analysis["clip_ids"][0]
    edit = orch.run_editing(clip_id)
    assert edit["clip_status"] == ClipStatus.APPROVED.value
    pub = orch.run_publishing(edit["render_id"])
    assert pub["success"] is True


def test_pause_agent(orch: Orchestrator) -> None:
    pause_agent(AgentName.DISCOVERY)
    assert is_agent_paused(AgentName.DISCOVERY)
    result = orch.run_discovery()
    assert result.get("paused") is True
    resume_agent(AgentName.DISCOVERY)
    assert not is_agent_paused(AgentName.DISCOVERY)


def test_reject_clip(orch: Orchestrator, sync_session: Session) -> None:
    disc = orch.run_discovery()
    analysis = orch.run_analysis(disc["created_ids"][0])
    clip_id = analysis["clip_ids"][0]
    orch.run_editing(clip_id)
    clip = orch.reject_clip(clip_id, notes="hook faible")
    assert clip.status == ClipStatus.REJECTED
    assert clip.review_notes == "hook faible"
