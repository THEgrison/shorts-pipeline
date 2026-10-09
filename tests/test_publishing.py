"""Publishing Agent tests with mocked platform APIs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from shorts_pipeline.agents.publishing.agent import PublishingAgent, PublishingInput
from shorts_pipeline.agents.publishing.base import PublishRequest
from shorts_pipeline.agents.publishing.copywriter import TemplateCopywriter
from shorts_pipeline.agents.publishing.instagram import InstagramReelsPublisher
from shorts_pipeline.agents.publishing.scheduler import next_slot
from shorts_pipeline.agents.publishing.tiktok import TikTokPublisher
from shorts_pipeline.agents.publishing.youtube import YouTubeShortsPublisher
from shorts_pipeline.config import Settings
from shorts_pipeline.db.enums import Platform
from shorts_pipeline.db.models import Account


def test_youtube_dry_run(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    result = YouTubeShortsPublisher().publish(
        PublishRequest(
            platform=Platform.YOUTUBE_SHORTS,
            video_path=video,
            title="Hello",
            description="Desc",
            hashtags=["#a"],
            idempotency_key="abc12345key",
            access_token="tok",
            dry_run=True,
        )
    )
    assert result.success and result.dry_run
    assert result.external_url and "youtube.com/shorts" in result.external_url


def test_youtube_resumable_upload(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"data" * 100)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "upload" in str(request.url):
            return httpx.Response(
                200,
                headers={"Location": "https://www.googleapis.com/upload/session/1"},
            )
        if request.method == "PUT":
            return httpx.Response(200, json={"id": "yt_vid_1"})
        return httpx.Response(404)

    pub = YouTubeShortsPublisher(transport=httpx.MockTransport(handler))
    result = pub.publish(
        PublishRequest(
            platform=Platform.YOUTUBE_SHORTS,
            video_path=video,
            title="Title",
            idempotency_key="key1",
            access_token="tok",
            dry_run=False,
        )
    )
    assert result.success
    assert result.external_post_id == "yt_vid_1"


def test_tiktok_init_and_upload(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"data" * 50)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/init/"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "upload_url": "https://upload.example/tiktok",
                        "publish_id": "pub_1",
                    }
                },
            )
        if "upload.example" in str(request.url):
            return httpx.Response(200)
        return httpx.Response(404)

    result = TikTokPublisher(transport=httpx.MockTransport(handler)).publish(
        PublishRequest(
            platform=Platform.TIKTOK,
            video_path=video,
            title="Hook",
            idempotency_key="tiktokkey1",
            access_token="tok",
            dry_run=False,
            privacy_status="private",
        )
    )
    assert result.success
    assert result.external_post_id == "pub_1"


def test_instagram_dry_run_and_missing_url(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    dry = InstagramReelsPublisher(ig_user_id="178414").publish(
        PublishRequest(
            platform=Platform.INSTAGRAM_REELS,
            video_path=video,
            title="T",
            idempotency_key="igkey1234",
            access_token="tok",
            dry_run=True,
        )
    )
    assert dry.success and dry.dry_run

    fail = InstagramReelsPublisher(ig_user_id="178414").publish(
        PublishRequest(
            platform=Platform.INSTAGRAM_REELS,
            video_path=video,
            title="T",
            idempotency_key="igkey5678",
            access_token="tok",
            dry_run=False,
        )
    )
    assert not fail.success
    assert "video_url" in (fail.error or "")


def test_publishing_agent_dry_run(tmp_path: Path, settings: Settings) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    agent = PublishingAgent(settings=settings, copywriter=TemplateCopywriter())
    out = agent.run(
        PublishingInput(
            render_id=1,
            account_id=1,
            platform=Platform.YOUTUBE_SHORTS,
            video_path=video,
            access_token="tok",
            seed_title="Mon hook",
            seed_hashtags=["#python"],
            idempotency_key="idemp-1",
            dry_run=True,
        )
    )
    assert out.success
    assert out.dry_run
    assert out.title == "Mon hook"
    assert "#Shorts" in out.hashtags or any("Shorts" in h for h in out.hashtags)


def test_scheduler_next_slot() -> None:
    account = Account(
        platform=Platform.YOUTUBE_SHORTS,
        display_name="A",
        external_account_id="a1",
        max_posts_per_day=5,
        schedule_config={"slots": ["23:59"], "timezone": "UTC"},
    )
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    slot = next_slot(account, now=now, jitter_seconds=0)
    assert slot.hour == 23 and slot.minute == 59
