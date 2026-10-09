"""Abstract Publisher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from shorts_pipeline.db.enums import Platform


class PublishRequest(BaseModel):
    """Normalized publish payload."""

    platform: Platform
    video_path: Path
    title: str
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    thumbnail_path: Path | None = None
    idempotency_key: str
    access_token: str
    dry_run: bool = True
    privacy_status: str = "private"  # safe default for TikTok audit / YT


class PublishResult(BaseModel):
    success: bool
    platform: Platform
    external_post_id: str | None = None
    external_url: str | None = None
    dry_run: bool = False
    error: str | None = None
    raw: dict[str, object] | None = None


class Publisher(ABC):
    """Platform-specific uploader."""

    platform: Platform

    @abstractmethod
    def publish(self, request: PublishRequest) -> PublishResult:
        """Upload a short. Must be idempotent given the same idempotency_key."""
