"""TikTok Content Posting API publisher."""

from __future__ import annotations

from typing import Any

import httpx

from shorts_pipeline.agents.publishing.base import Publisher, PublishRequest, PublishResult
from shorts_pipeline.db.enums import Platform
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class TikTokPublisher(Publisher):
    """
    Official Content Posting API (inbox/direct post).

    Defaults to `privacy_level=SELF_ONLY` when not explicitly public, which
    satisfies unaudited app constraints during development.
    """

    platform = Platform.TIKTOK
    BASE = "https://open.tiktokapis.com"

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=self.BASE,
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def publish(self, request: PublishRequest) -> PublishResult:
        if request.dry_run:
            url = f"https://www.tiktok.com/@dry/video/{request.idempotency_key[:8]}"
            logger.info("tiktok.dry_run", key=request.idempotency_key)
            return PublishResult(
                success=True,
                platform=self.platform,
                external_post_id=f"dry-{request.idempotency_key}",
                external_url=url,
                dry_run=True,
            )

        privacy = "PUBLIC_TO_EVERYONE" if request.privacy_status == "public" else "SELF_ONLY"
        caption = self._caption(request)
        headers = {
            "Authorization": f"Bearer {request.access_token}",
            "Content-Type": "application/json",
        }

        # 1) Init upload
        init_body = {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": request.video_path.stat().st_size,
                "chunk_size": request.video_path.stat().st_size,
                "total_chunk_count": 1,
            },
        }
        init = self._client.post(
            "/v2/post/publish/video/init/",
            headers=headers,
            json=init_body,
        )
        init.raise_for_status()
        init_data: dict[str, Any] = init.json()
        upload_url = (init_data.get("data") or {}).get("upload_url")
        publish_id = (init_data.get("data") or {}).get("publish_id")
        if not upload_url:
            return PublishResult(
                success=False,
                platform=self.platform,
                error=f"TikTok init failed: {init_data}",
                raw=init_data,
            )

        # 2) Upload binary
        with request.video_path.open("rb") as fh:
            put = self._client.put(
                upload_url,
                content=fh,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(request.video_path.stat().st_size),
                },
            )
        put.raise_for_status()

        logger.info("tiktok.published", publish_id=publish_id)
        return PublishResult(
            success=True,
            platform=self.platform,
            external_post_id=publish_id,
            external_url=None,  # TikTok may not return public URL immediately
            dry_run=False,
            raw=init_data,
        )

    @staticmethod
    def _caption(request: PublishRequest) -> str:
        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in request.hashtags)
        return f"{request.title}\n\n{request.description}\n{tags}".strip()
