"""YouTube Shorts publisher (Data API resumable upload)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from shorts_pipeline.agents.publishing.base import Publisher, PublishRequest, PublishResult
from shorts_pipeline.db.enums import Platform
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class YouTubeShortsPublisher(Publisher):
    """Upload via YouTube Data API v3 videos.insert (resumable)."""

    platform = Platform.YOUTUBE_SHORTS

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def publish(self, request: PublishRequest) -> PublishResult:
        if request.dry_run:
            url = f"https://youtube.com/shorts/dry-run-{request.idempotency_key[:8]}"
            logger.info("youtube.dry_run", key=request.idempotency_key)
            return PublishResult(
                success=True,
                platform=self.platform,
                external_post_id=f"dry-{request.idempotency_key}",
                external_url=url,
                dry_run=True,
            )

        title = request.title[:100]
        description = self._build_description(request)
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": request.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        headers = {
            "Authorization": f"Bearer {request.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(request.video_path.stat().st_size),
        }
        init = self._client.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers=headers,
            content=json.dumps(metadata).encode("utf-8"),
        )
        init.raise_for_status()
        upload_url = init.headers.get("Location")
        if not upload_url:
            return PublishResult(
                success=False,
                platform=self.platform,
                error="Missing resumable upload Location header",
            )

        with request.video_path.open("rb") as fh:
            put = self._client.put(
                upload_url,
                content=fh,
                headers={
                    "Authorization": f"Bearer {request.access_token}",
                    "Content-Type": "video/mp4",
                },
            )
        put.raise_for_status()
        data: dict[str, Any] = put.json()
        video_id_val = data.get("id")
        video_id = str(video_id_val) if video_id_val else None
        external_url: str | None = f"https://youtube.com/shorts/{video_id}" if video_id else None
        logger.info("youtube.published", video_id=video_id)
        return PublishResult(
            success=True,
            platform=self.platform,
            external_post_id=video_id,
            external_url=external_url,
            dry_run=False,
            raw=data,
        )

    @staticmethod
    def _build_description(request: PublishRequest) -> str:
        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in request.hashtags)
        body = request.description.strip()
        # Shorts convention
        suffix = "\n\n#Shorts"
        return f"{body}\n{tags}{suffix}".strip()
