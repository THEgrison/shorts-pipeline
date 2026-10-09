"""Publishing Agent: schedule + upload via platform publishers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from pydantic import Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shorts_pipeline.agents.base import Agent, AgentInput, AgentOutput
from shorts_pipeline.agents.publishing.base import Publisher, PublishRequest, PublishResult
from shorts_pipeline.agents.publishing.copywriter import Copywriter, TemplateCopywriter
from shorts_pipeline.agents.publishing.instagram import InstagramReelsPublisher
from shorts_pipeline.agents.publishing.tiktok import TikTokPublisher
from shorts_pipeline.agents.publishing.youtube import YouTubeShortsPublisher
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.db.enums import AgentName, Platform
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class PublishingInput(AgentInput):
    render_id: int
    account_id: int
    platform: Platform
    video_path: Path
    access_token: str
    seed_title: str | None = None
    seed_description: str | None = None
    seed_hashtags: list[str] = Field(default_factory=list)
    idempotency_key: str
    thumbnail_path: Path | None = None
    privacy_status: str = "private"
    language: str = "fr"
    ig_user_id: str | None = None


class PublishingOutput(AgentOutput):
    render_id: int
    account_id: int
    platform: Platform
    title: str | None = None
    description: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    external_post_id: str | None = None
    external_url: str | None = None
    dry_run: bool = True
    raw: dict[str, Any] | None = None


class PublishingAgent(Agent[PublishingInput, PublishingOutput]):
    name = AgentName.PUBLISHING

    def __init__(
        self,
        *,
        publishers: dict[Platform, Publisher] | None = None,
        copywriter: Copywriter | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.copywriter = copywriter or TemplateCopywriter()
        self.publishers = publishers or {
            Platform.YOUTUBE_SHORTS: YouTubeShortsPublisher(),
            Platform.TIKTOK: TikTokPublisher(),
        }

    def run(self, input_data: PublishingInput) -> PublishingOutput:
        dry_run = input_data.dry_run or self.settings.dry_run
        copy = self.copywriter.generate(
            platform=input_data.platform,
            seed_title=input_data.seed_title,
            seed_description=input_data.seed_description,
            seed_hashtags=input_data.seed_hashtags,
            language=input_data.language,
        )
        publisher = self._get_publisher(input_data)
        request = PublishRequest(
            platform=input_data.platform,
            video_path=input_data.video_path,
            title=copy.title,
            description=copy.description,
            hashtags=copy.hashtags,
            thumbnail_path=input_data.thumbnail_path,
            idempotency_key=input_data.idempotency_key,
            access_token=input_data.access_token,
            dry_run=dry_run,
            privacy_status=input_data.privacy_status,
        )
        result = self._publish_with_retry(publisher, request)
        return PublishingOutput(
            success=result.success,
            message="published" if result.success else (result.error or "failed"),
            error=result.error,
            render_id=input_data.render_id,
            account_id=input_data.account_id,
            platform=input_data.platform,
            title=copy.title,
            description=copy.description,
            hashtags=copy.hashtags,
            external_post_id=result.external_post_id,
            external_url=result.external_url,
            dry_run=result.dry_run,
            raw=result.raw,
        )

    def _get_publisher(self, input_data: PublishingInput) -> Publisher:
        if input_data.platform in self.publishers:
            return self.publishers[input_data.platform]
        if input_data.platform == Platform.INSTAGRAM_REELS:
            if not input_data.ig_user_id:
                msg = "ig_user_id required for Instagram publishing"
                raise ValueError(msg)
            return InstagramReelsPublisher(ig_user_id=input_data.ig_user_id)
        msg = f"No publisher registered for {input_data.platform}"
        raise ValueError(msg)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _publish_with_retry(self, publisher: Publisher, request: PublishRequest) -> PublishResult:
        try:
            return publisher.publish(request)
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code in {429, 500, 502, 503, 504}:
                logger.warning(
                    "publishing.retryable_http",
                    status=exc.response.status_code,
                    platform=request.platform.value,
                )
            raise
