"""Discovery Agent: find authorized, high-relevance YouTube videos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import Field

from shorts_pipeline.agents.base import Agent, AgentInput, AgentOutput
from shorts_pipeline.agents.discovery.license_filter import authorize_video
from shorts_pipeline.agents.discovery.niches import DiscoveryConfig, load_discovery_config
from shorts_pipeline.agents.discovery.scoring import compute_relevance_score
from shorts_pipeline.clients.youtube import YouTubeClient, YouTubeVideoSnippet
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.db.enums import AgentName, LicenseBasis
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class DiscoveredVideo(AgentOutput):
    """A single video retained after license + scoring filters."""

    youtube_video_id: str
    youtube_channel_id: str
    title: str
    description: str | None = None
    published_at: datetime | None = None
    duration_sec: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    language: str | None = None
    license: str | None = None
    license_basis: LicenseBasis
    relevance_score: float
    thumbnail_url: str | None = None
    raw_metadata: dict[str, Any] | None = None


class DiscoveryInput(AgentInput):
    niches: list[str] = Field(default_factory=list, description="Niche names to run; empty = all")
    already_seen_ids: set[str] = Field(default_factory=set)
    whitelist_channel_ids: set[str] = Field(default_factory=set)
    config_path: Path | None = None
    published_within_days: int = 30
    min_score: float = 25.0


class DiscoveryOutput(AgentOutput):
    videos: list[DiscoveredVideo] = Field(default_factory=list)
    skipped_unauthorized: int = 0
    skipped_duplicate: int = 0
    skipped_low_score: int = 0
    quota_remaining: int | None = None


class DiscoveryAgent(Agent[DiscoveryInput, DiscoveryOutput]):
    """Search YouTube, enforce license filter, score, dedupe."""

    name = AgentName.DISCOVERY

    def __init__(
        self,
        client: YouTubeClient,
        *,
        settings: Settings | None = None,
        discovery_config: DiscoveryConfig | None = None,
    ) -> None:
        self.client = client
        self.settings = settings or get_settings()
        self.discovery_config = discovery_config

    def run(self, input_data: DiscoveryInput) -> DiscoveryOutput:
        config = self.discovery_config or load_discovery_config(input_data.config_path)
        niches = config.niches
        if input_data.niches:
            wanted = set(input_data.niches)
            niches = [n for n in niches if n.name in wanted]

        published_after = datetime.now(UTC) - timedelta(days=input_data.published_within_days)
        candidate_ids: list[str] = []
        seen_batch: set[str] = set()

        for niche in niches:
            languages: list[str | None]
            if niche.languages:
                languages = [*niche.languages]
            elif self.settings.allowed_languages_list:
                languages = [*self.settings.allowed_languages_list]
            else:
                languages = [None]

            for keyword in niche.keywords:
                for lang in languages:
                    # Prefer Creative Commons search to save quota on unauthorized standard videos
                    ids_cc = self.client.search_videos(
                        keyword,
                        max_results=self.settings.discovery_max_results_per_query,
                        published_after=published_after,
                        relevance_language=lang,
                        video_license="creativeCommon",
                    )
                    for vid in ids_cc:
                        if vid not in seen_batch:
                            seen_batch.add(vid)
                            candidate_ids.append(vid)

                    # Also search generally — whitelist will authorize owned channels
                    if input_data.whitelist_channel_ids:
                        ids_all = self.client.search_videos(
                            keyword,
                            max_results=min(10, self.settings.discovery_max_results_per_query),
                            published_after=published_after,
                            relevance_language=lang,
                        )
                        for vid in ids_all:
                            if vid not in seen_batch:
                                seen_batch.add(vid)
                                candidate_ids.append(vid)

        # Deduplicate against already processed
        skipped_duplicate = 0
        fresh_ids: list[str] = []
        for vid in candidate_ids:
            if vid in input_data.already_seen_ids:
                skipped_duplicate += 1
            else:
                fresh_ids.append(vid)

        details = self.client.get_videos(fresh_ids)
        kept: list[DiscoveredVideo] = []
        skipped_unauthorized = 0
        skipped_low_score = 0

        for video in details:
            auth = authorize_video(video, whitelist_channel_ids=input_data.whitelist_channel_ids)
            if not auth.allowed or auth.basis is None:
                skipped_unauthorized += 1
                logger.info(
                    "discovery.rejected_license",
                    video_id=video.video_id,
                    reason=auth.reason,
                )
                continue

            if not self._duration_ok(video):
                skipped_low_score += 1
                continue

            score = compute_relevance_score(video, settings=self.settings)
            if score < input_data.min_score:
                skipped_low_score += 1
                continue

            assert auth.basis is not None
            kept.append(
                DiscoveredVideo(
                    success=True,
                    youtube_video_id=video.video_id,
                    youtube_channel_id=video.channel_id,
                    title=video.title,
                    description=video.description,
                    published_at=video.published_at,
                    duration_sec=video.duration_sec,
                    view_count=video.view_count,
                    like_count=video.like_count,
                    comment_count=video.comment_count,
                    language=video.language,
                    license=video.license,
                    license_basis=auth.basis,
                    relevance_score=score,
                    thumbnail_url=video.thumbnail_url,
                    raw_metadata=video.raw,
                )
            )

        kept.sort(key=lambda v: v.relevance_score, reverse=True)
        logger.info(
            "discovery.completed",
            kept=len(kept),
            skipped_unauthorized=skipped_unauthorized,
            skipped_duplicate=skipped_duplicate,
            skipped_low_score=skipped_low_score,
            quota_remaining=self.client.quota.remaining(),
        )
        return DiscoveryOutput(
            success=True,
            message=f"Discovered {len(kept)} videos",
            videos=kept,
            skipped_unauthorized=skipped_unauthorized,
            skipped_duplicate=skipped_duplicate,
            skipped_low_score=skipped_low_score,
            quota_remaining=self.client.quota.remaining(),
        )

    def _duration_ok(self, video: YouTubeVideoSnippet) -> bool:
        dur = video.duration_sec or 0
        if dur <= 0:
            return False
        return (
            self.settings.discovery_ideal_duration_min_sec * 0.5
            <= dur
            <= self.settings.discovery_ideal_duration_max_sec * 1.5
        )
