"""Shared domain enums for pipeline state machines."""

from __future__ import annotations

from enum import StrEnum


class VideoStatus(StrEnum):
    """Lifecycle of a discovered source video."""

    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    TRANSCRIBED = "transcribed"
    ANALYZED = "analyzed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ClipStatus(StrEnum):
    """Lifecycle of a detected clip."""

    ANALYZED = "analyzed"
    RENDERED = "rendered"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class RenderStatus(StrEnum):
    """Lifecycle of a rendered short."""

    PENDING = "pending"
    RENDERING = "rendering"
    RENDERED = "rendered"
    FAILED = "failed"


class PublicationStatus(StrEnum):
    """Lifecycle of a platform publication."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class LicenseBasis(StrEnum):
    """Why a video is allowed to be processed."""

    WHITELIST = "whitelist"
    CREATIVE_COMMONS = "creative_commons"


class Platform(StrEnum):
    """Supported publishing platforms."""

    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    INSTAGRAM_REELS = "instagram_reels"


class JobStatus(StrEnum):
    """Celery / orchestrator job log status."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class AgentName(StrEnum):
    """Agent identifiers."""

    DISCOVERY = "discovery"
    ANALYSIS = "analysis"
    EDITING = "editing"
    PUBLISHING = "publishing"
    ORCHESTRATOR = "orchestrator"
    CLEANUP = "cleanup"
