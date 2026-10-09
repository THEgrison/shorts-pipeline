"""YouTube Data API v3 client with quota accounting and response cache."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from shorts_pipeline.clients.base import BaseHttpClient, RateLimiter
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.metrics import YOUTUBE_QUOTA_REMAINING

logger = get_logger(__name__)

QUOTA_SEARCH = 100
QUOTA_VIDEOS_LIST = 1
QUOTA_CHANNELS_LIST = 1

_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


@dataclass(frozen=True, slots=True)
class YouTubeVideoSnippet:
    """Normalized video metadata from the Data API."""

    video_id: str
    channel_id: str
    channel_title: str
    title: str
    description: str
    published_at: datetime | None
    duration_sec: int | None
    view_count: int
    like_count: int
    comment_count: int
    language: str | None
    license: str  # "youtube" | "creativeCommon"
    tags: list[str]
    thumbnail_url: str | None
    raw: dict[str, Any]


class QuotaExceededError(RuntimeError):
    """Raised when the daily YouTube quota budget is exhausted."""


class YouTubeQuotaTracker:
    """In-memory (+ optional Redis) daily quota counter."""

    def __init__(self, *, daily_limit: int, redis_url: str | None = None) -> None:
        self.daily_limit = daily_limit
        self._local_used = 0
        self._local_day = datetime.now(UTC).date().isoformat()
        self._redis: Any = None
        if redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
            except Exception:
                self._redis = None

    def _day_key(self) -> str:
        return f"shorts_pipeline:yt_quota:{datetime.now(UTC).date().isoformat()}"

    def used(self) -> int:
        if self._redis is not None:
            try:
                val = self._redis.get(self._day_key())
                return int(val or 0)
            except Exception:
                pass
        today = datetime.now(UTC).date().isoformat()
        if today != self._local_day:
            self._local_day = today
            self._local_used = 0
        return self._local_used

    def remaining(self) -> int:
        return max(0, self.daily_limit - self.used())

    def consume(self, units: int) -> None:
        if self.used() + units > self.daily_limit:
            YOUTUBE_QUOTA_REMAINING.set(self.remaining())
            msg = f"YouTube quota exceeded (need {units}, remaining {self.remaining()})"
            raise QuotaExceededError(msg)
        if self._redis is not None:
            try:
                key = self._day_key()
                pipe = self._redis.pipeline()
                pipe.incrby(key, units)
                pipe.expire(key, 60 * 60 * 48)
                pipe.execute()
                YOUTUBE_QUOTA_REMAINING.set(self.remaining())
                return
            except Exception:
                logger.warning("youtube.quota_redis_fallback")
        today = datetime.now(UTC).date().isoformat()
        if today != self._local_day:
            self._local_day = today
            self._local_used = 0
        self._local_used += units
        YOUTUBE_QUOTA_REMAINING.set(self.remaining())


class ResponseCache:
    """Simple TTL cache for API JSON responses (memory)."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    @staticmethod
    def make_key(path: str, params: dict[str, Any]) -> str:
        raw = path + "?" + json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        expires, value = item
        if time.monotonic() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self.ttl_seconds, value)


def parse_iso8601_duration(value: str) -> int:
    """Parse YouTube ISO-8601 duration (PT#H#M#S) to seconds."""
    match = _DURATION_RE.fullmatch(value or "")
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def license_from_item(item: dict[str, Any]) -> str:
    """Extract license from a videos.list item."""
    status = item.get("status") or {}
    lic = status.get("license")
    if lic in {"youtube", "creativeCommon"}:
        return str(lic)
    return "youtube"


class YouTubeClient(BaseHttpClient):
    """Thin YouTube Data API v3 wrapper."""

    def __init__(
        self,
        *,
        api_key: str,
        settings: Settings | None = None,
        quota: YouTubeQuotaTracker | None = None,
        cache: ResponseCache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.api_key = api_key
        self.settings = cfg
        self.quota = quota or YouTubeQuotaTracker(
            daily_limit=cfg.youtube_quota_daily_limit,
            redis_url=cfg.redis_url,
        )
        self.cache = cache or ResponseCache(ttl_seconds=3600)
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.timeout = 30.0
        self.rate_limiter = RateLimiter(max_calls=30, period_seconds=1.0)
        self._headers: dict[str, str] = {}
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
            follow_redirects=True,
        )

    def _get(self, path: str, params: dict[str, Any], *, quota_cost: int) -> dict[str, Any]:
        params = {**params, "key": self.api_key}
        cache_key = ResponseCache.make_key(path, {k: v for k, v in params.items() if k != "key"})
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("youtube.cache_hit", path=path)
            return cached  # type: ignore[no-any-return]

        self.quota.consume(quota_cost)
        # RateLimiter expects acquire before request
        if self.rate_limiter:
            self.rate_limiter.acquire()
        response = self._client.request("GET", path, params=params)
        response.raise_for_status()
        data = response.json()
        self.cache.set(cache_key, data)
        return data  # type: ignore[no-any-return]

    def search_videos(
        self,
        query: str,
        *,
        max_results: int = 25,
        published_after: datetime | None = None,
        relevance_language: str | None = None,
        video_license: str | None = None,
    ) -> list[str]:
        """Return video IDs matching a search query."""
        params: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": min(max_results, 50),
            "order": "relevance",
        }
        if published_after:
            params["publishedAfter"] = published_after.astimezone(UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        if video_license:
            params["videoLicense"] = video_license

        data = self._get("/search", params, quota_cost=QUOTA_SEARCH)
        ids: list[str] = []
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        return ids

    def get_videos(self, video_ids: list[str]) -> list[YouTubeVideoSnippet]:
        """Fetch detailed metadata for up to 50 video IDs per request."""
        if not video_ids:
            return []
        results: list[YouTubeVideoSnippet] = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            data = self._get(
                "/videos",
                {
                    "part": "snippet,contentDetails,statistics,status",
                    "id": ",".join(chunk),
                },
                quota_cost=QUOTA_VIDEOS_LIST,
            )
            for item in data.get("items", []):
                results.append(self._parse_video(item))
        return results

    def get_channel(self, channel_id: str) -> dict[str, Any]:
        data = self._get(
            "/channels",
            {"part": "snippet,statistics", "id": channel_id},
            quota_cost=QUOTA_CHANNELS_LIST,
        )
        items = data.get("items") or []
        if not items:
            return {}
        first: dict[str, Any] = items[0]
        return first

    @staticmethod
    def _parse_video(item: dict[str, Any]) -> YouTubeVideoSnippet:
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        details = item.get("contentDetails") or {}
        published_raw = snippet.get("publishedAt")
        published_at: datetime | None = None
        if published_raw:
            published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        thumbs = snippet.get("thumbnails") or {}
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get(
            "url"
        )
        return YouTubeVideoSnippet(
            video_id=item["id"],
            channel_id=snippet.get("channelId", ""),
            channel_title=snippet.get("channelTitle", ""),
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            published_at=published_at,
            duration_sec=parse_iso8601_duration(details.get("duration", "")),
            view_count=int(stats.get("viewCount") or 0),
            like_count=int(stats.get("likeCount") or 0),
            comment_count=int(stats.get("commentCount") or 0),
            language=snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
            license=license_from_item(item),
            tags=list(snippet.get("tags") or []),
            thumbnail_url=thumb,
            raw=item,
        )
