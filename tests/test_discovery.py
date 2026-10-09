"""Discovery Agent unit tests with mocked YouTube API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session

from shorts_pipeline.agents.discovery.agent import DiscoveryAgent, DiscoveryInput
from shorts_pipeline.agents.discovery.license_filter import authorize_video
from shorts_pipeline.agents.discovery.niches import load_discovery_config
from shorts_pipeline.agents.discovery.scoring import compute_relevance_score
from shorts_pipeline.clients.youtube import (
    QuotaExceededError,
    YouTubeClient,
    YouTubeQuotaTracker,
    YouTubeVideoSnippet,
    parse_iso8601_duration,
)
from shorts_pipeline.config import Settings
from shorts_pipeline.db.enums import LicenseBasis, VideoStatus
from shorts_pipeline.db.models import ChannelWhitelist, SourceVideo
from shorts_pipeline.orchestrator.service import Orchestrator


def _video_item(
    video_id: str,
    *,
    channel_id: str = "UCother",
    license_: str = "youtube",
    duration: str = "PT20M",
    views: str = "50000",
    likes: str = "2500",
    language: str = "fr",
    published_at: str | None = None,
    title: str = "Tutorial Python",
) -> dict:
    pub = published_at or (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": video_id,
        "snippet": {
            "channelId": channel_id,
            "channelTitle": "Some Channel",
            "title": title,
            "description": "desc",
            "publishedAt": pub,
            "defaultAudioLanguage": language,
            "thumbnails": {"high": {"url": "https://img.example/h.jpg"}},
            "tags": ["python"],
        },
        "contentDetails": {"duration": duration},
        "statistics": {
            "viewCount": views,
            "likeCount": likes,
            "commentCount": "100",
        },
        "status": {"license": license_},
    }


@pytest.fixture
def mock_youtube(settings: Settings) -> YouTubeClient:
    search_cc = {
        "items": [
            {"id": {"videoId": "cc_good"}},
            {"id": {"videoId": "std_blocked"}},
        ]
    }
    search_all = {
        "items": [
            {"id": {"videoId": "owned_vid"}},
            {"id": {"videoId": "std_blocked"}},
        ]
    }
    videos = {
        "items": [
            _video_item("cc_good", license_="creativeCommon", channel_id="UCcc"),
            _video_item("std_blocked", license_="youtube", channel_id="UCblocked"),
            _video_item("owned_vid", license_="youtube", channel_id="UCmine", title="Ma vidéo"),
        ]
    }

    by_id = {item["id"]: item for item in videos["items"]}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        if path.endswith("/search"):
            if params.get("videoLicense") == "creativeCommon":
                return httpx.Response(200, json=search_cc)
            return httpx.Response(200, json=search_all)
        if path.endswith("/videos"):
            requested = [v for v in (params.get("id") or "").split(",") if v]
            items = [by_id[i] for i in requested if i in by_id]
            return httpx.Response(200, json={"items": items})
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    quota = YouTubeQuotaTracker(daily_limit=10_000, redis_url=None)
    return YouTubeClient(
        api_key="test-key",
        settings=settings,
        quota=quota,
        transport=transport,
    )


def test_parse_duration() -> None:
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("PT15M") == 900
    assert parse_iso8601_duration("bad") == 0


def test_license_filter_cc() -> None:
    video = YouTubeVideoSnippet(
        video_id="1",
        channel_id="UCx",
        channel_title="x",
        title="t",
        description="",
        published_at=datetime.now(UTC),
        duration_sec=600,
        view_count=100,
        like_count=10,
        comment_count=1,
        language="fr",
        license="creativeCommon",
        tags=[],
        thumbnail_url=None,
        raw={},
    )
    result = authorize_video(video, whitelist_channel_ids=set())
    assert result.allowed
    assert result.basis == LicenseBasis.CREATIVE_COMMONS


def test_license_filter_whitelist() -> None:
    video = YouTubeVideoSnippet(
        video_id="1",
        channel_id="UCmine",
        channel_title="me",
        title="t",
        description="",
        published_at=datetime.now(UTC),
        duration_sec=600,
        view_count=100,
        like_count=10,
        comment_count=1,
        language="fr",
        license="youtube",
        tags=[],
        thumbnail_url=None,
        raw={},
    )
    denied = authorize_video(video, whitelist_channel_ids=set())
    assert not denied.allowed
    allowed = authorize_video(video, whitelist_channel_ids={"UCmine"})
    assert allowed.allowed
    assert allowed.basis == LicenseBasis.WHITELIST


def test_scoring_prefers_fresh_engaging(settings: Settings) -> None:
    now = datetime.now(UTC)
    hot = YouTubeVideoSnippet(
        video_id="h",
        channel_id="c",
        channel_title="c",
        title="t",
        description="",
        published_at=now - timedelta(hours=6),
        duration_sec=900,
        view_count=50_000,
        like_count=3_000,
        comment_count=200,
        language="fr",
        license="creativeCommon",
        tags=[],
        thumbnail_url=None,
        raw={},
    )
    cold = YouTubeVideoSnippet(
        video_id="c",
        channel_id="c",
        channel_title="c",
        title="t",
        description="",
        published_at=now - timedelta(days=400),
        duration_sec=60,
        view_count=10,
        like_count=0,
        comment_count=0,
        language="de",
        license="creativeCommon",
        tags=[],
        thumbnail_url=None,
        raw={},
    )
    assert compute_relevance_score(hot, settings=settings, now=now) > compute_relevance_score(
        cold, settings=settings, now=now
    )


def test_discovery_agent_keeps_cc_and_whitelist(
    mock_youtube: YouTubeClient, settings: Settings, tmp_path: Path
) -> None:
    niches_yaml = tmp_path / "niches.yaml"
    niches_yaml.write_text(
        """
niches:
  - name: tech_fr
    keywords: ["python"]
    languages: [fr]
seed_channels: []
""",
        encoding="utf-8",
    )
    agent = DiscoveryAgent(
        mock_youtube,
        settings=settings,
        discovery_config=load_discovery_config(niches_yaml),
    )
    out = agent.run(
        DiscoveryInput(
            niches=["tech_fr"],
            whitelist_channel_ids={"UCmine"},
            already_seen_ids=set(),
            min_score=10.0,
            config_path=niches_yaml,
        )
    )
    ids = {v.youtube_video_id for v in out.videos}
    assert "cc_good" in ids
    assert "owned_vid" in ids
    assert "std_blocked" not in ids
    assert out.skipped_unauthorized >= 1
    bases = {v.youtube_video_id: v.license_basis for v in out.videos}
    assert bases["cc_good"] == LicenseBasis.CREATIVE_COMMONS
    assert bases["owned_vid"] == LicenseBasis.WHITELIST


def test_discovery_dedup(mock_youtube: YouTubeClient, settings: Settings, tmp_path: Path) -> None:
    niches_yaml = tmp_path / "niches.yaml"
    niches_yaml.write_text(
        """
niches:
  - name: tech_fr
    keywords: ["python"]
    languages: [fr]
""",
        encoding="utf-8",
    )
    agent = DiscoveryAgent(
        mock_youtube,
        settings=settings,
        discovery_config=load_discovery_config(niches_yaml),
    )
    out = agent.run(
        DiscoveryInput(
            niches=["tech_fr"],
            whitelist_channel_ids={"UCmine"},
            already_seen_ids={"cc_good"},
            min_score=10.0,
        )
    )
    ids = {v.youtube_video_id for v in out.videos}
    assert "cc_good" not in ids
    assert out.skipped_duplicate >= 1


def test_persist_and_orchestrator(
    mock_youtube: YouTubeClient,
    sync_session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    sync_session.add(
        ChannelWhitelist(
            youtube_channel_id="UCmine",
            title="Mine",
            is_owned=True,
            is_active=True,
        )
    )
    sync_session.commit()

    niches_yaml = tmp_path / "niches.yaml"
    niches_yaml.write_text(
        """
niches:
  - name: tech_fr
    keywords: ["python"]
    languages: [fr]
""",
        encoding="utf-8",
    )
    agent = DiscoveryAgent(
        mock_youtube,
        settings=settings,
        discovery_config=load_discovery_config(niches_yaml),
    )
    orch = Orchestrator(
        sync_session,
        settings=settings,
        discovery_agent=agent,
        youtube_client=mock_youtube,
    )
    # Monkeypatch load config path via agent already having discovery_config
    result = orch.run_discovery(niches=["tech_fr"])
    assert result["success"] is True
    assert len(result["created_ids"]) >= 2
    rows = sync_session.query(SourceVideo).all()
    assert all(r.status == VideoStatus.DISCOVERED for r in rows)
    assert all(r.license_basis is not None for r in rows)

    # Second run: no duplicates
    result2 = orch.run_discovery(niches=["tech_fr"])
    assert result2["created_ids"] == []


def test_quota_exceeded(settings: Settings) -> None:
    quota = YouTubeQuotaTracker(daily_limit=50, redis_url=None)
    quota.consume(50)
    with pytest.raises(QuotaExceededError):
        quota.consume(1)


def test_cache_avoids_second_quota(settings: Settings) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"items": [{"id": {"videoId": "x"}}]},
        )

    client = YouTubeClient(
        api_key="k",
        settings=settings,
        quota=YouTubeQuotaTracker(daily_limit=1000, redis_url=None),
        transport=httpx.MockTransport(handler),
    )
    client.search_videos("q", max_results=5)
    used_after_first = client.quota.used()
    client.search_videos("q", max_results=5)
    assert client.quota.used() == used_after_first
    assert calls["n"] == 1
