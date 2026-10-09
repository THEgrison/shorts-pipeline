"""Dummy agents used in Phase 2 to validate the orchestration flow."""

from __future__ import annotations

from pydantic import Field

from shorts_pipeline.agents.base import Agent, AgentInput, AgentOutput
from shorts_pipeline.db.enums import AgentName
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class DummyDiscoveryInput(AgentInput):
    niches: list[str] = Field(default_factory=list)


class DummyDiscoveryOutput(AgentOutput):
    videos_found: int = 0
    video_ids: list[str] = Field(default_factory=list)


class DummyDiscoveryAgent(Agent[DummyDiscoveryInput, DummyDiscoveryOutput]):
    """Fake discovery: returns a synthetic Creative Commons video id."""

    name = AgentName.DISCOVERY

    def run(self, input_data: DummyDiscoveryInput) -> DummyDiscoveryOutput:
        video_id = "dummy_cc_video_001"
        logger.info("dummy.discovery", niches=input_data.niches, video_id=video_id)
        return DummyDiscoveryOutput(
            success=True,
            message="Dummy discovery completed",
            videos_found=1,
            video_ids=[video_id],
        )


class DummyAnalysisInput(AgentInput):
    source_video_id: int
    youtube_video_id: str


class DummyAnalysisOutput(AgentOutput):
    clips_created: int = 0
    clip_ids: list[int] = Field(default_factory=list)


class DummyAnalysisAgent(Agent[DummyAnalysisInput, DummyAnalysisOutput]):
    """Fake analysis: pretends to create one clip (DB write done by orchestrator)."""

    name = AgentName.ANALYSIS

    def run(self, input_data: DummyAnalysisInput) -> DummyAnalysisOutput:
        logger.info(
            "dummy.analysis",
            source_video_id=input_data.source_video_id,
            youtube_video_id=input_data.youtube_video_id,
        )
        return DummyAnalysisOutput(
            success=True,
            message="Dummy analysis completed",
            clips_created=1,
        )


class DummyEditingInput(AgentInput):
    clip_id: int


class DummyEditingOutput(AgentOutput):
    render_id: int | None = None
    storage_key: str | None = None


class DummyEditingAgent(Agent[DummyEditingInput, DummyEditingOutput]):
    """Fake editing: returns a placeholder storage key."""

    name = AgentName.EDITING

    def run(self, input_data: DummyEditingInput) -> DummyEditingOutput:
        key = f"renders/dummy_clip_{input_data.clip_id}.mp4"
        logger.info("dummy.editing", clip_id=input_data.clip_id, storage_key=key)
        return DummyEditingOutput(
            success=True,
            message="Dummy edit completed",
            storage_key=key,
        )


class DummyPublishingInput(AgentInput):
    render_id: int
    account_id: int | None = None


class DummyPublishingOutput(AgentOutput):
    publication_id: int | None = None
    external_url: str | None = None


class DummyPublishingAgent(Agent[DummyPublishingInput, DummyPublishingOutput]):
    """Fake publishing: respects dry_run (never hits real APIs)."""

    name = AgentName.PUBLISHING

    def run(self, input_data: DummyPublishingInput) -> DummyPublishingOutput:
        url = f"https://example.com/dry-run/render/{input_data.render_id}"
        logger.info(
            "dummy.publishing",
            render_id=input_data.render_id,
            dry_run=input_data.dry_run,
            url=url,
        )
        return DummyPublishingOutput(
            success=True,
            message="Dummy publish completed (dry-run safe)",
            external_url=url,
        )
