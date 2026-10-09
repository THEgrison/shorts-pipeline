"""Idempotent state transitions for videos and clips."""

from __future__ import annotations

from dataclasses import dataclass

from shorts_pipeline.db.enums import ClipStatus, VideoStatus


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed."""


# video: discovered → downloaded → transcribed → analyzed → failed|skipped
VIDEO_TRANSITIONS: dict[VideoStatus, frozenset[VideoStatus]] = {
    VideoStatus.DISCOVERED: frozenset(
        {VideoStatus.DOWNLOADED, VideoStatus.FAILED, VideoStatus.SKIPPED}
    ),
    VideoStatus.DOWNLOADED: frozenset(
        {VideoStatus.TRANSCRIBED, VideoStatus.FAILED, VideoStatus.SKIPPED}
    ),
    VideoStatus.TRANSCRIBED: frozenset(
        {VideoStatus.ANALYZED, VideoStatus.FAILED, VideoStatus.SKIPPED}
    ),
    VideoStatus.ANALYZED: frozenset({VideoStatus.FAILED}),  # terminal success path
    VideoStatus.FAILED: frozenset(
        {
            VideoStatus.DISCOVERED,
            VideoStatus.DOWNLOADED,
            VideoStatus.TRANSCRIBED,
        }
    ),  # retry from last safe step
    VideoStatus.SKIPPED: frozenset(),
}

# clip: analyzed → rendered → awaiting_review → approved → scheduled → published
CLIP_TRANSITIONS: dict[ClipStatus, frozenset[ClipStatus]] = {
    ClipStatus.ANALYZED: frozenset({ClipStatus.RENDERED, ClipStatus.FAILED, ClipStatus.REJECTED}),
    ClipStatus.RENDERED: frozenset(
        {
            ClipStatus.AWAITING_REVIEW,
            ClipStatus.APPROVED,
            ClipStatus.SCHEDULED,
            ClipStatus.FAILED,
            ClipStatus.REJECTED,
        }
    ),
    ClipStatus.AWAITING_REVIEW: frozenset(
        {ClipStatus.APPROVED, ClipStatus.REJECTED, ClipStatus.FAILED}
    ),
    ClipStatus.APPROVED: frozenset({ClipStatus.SCHEDULED, ClipStatus.FAILED}),
    ClipStatus.SCHEDULED: frozenset({ClipStatus.PUBLISHED, ClipStatus.FAILED}),
    ClipStatus.PUBLISHED: frozenset(),
    ClipStatus.REJECTED: frozenset({ClipStatus.ANALYZED}),  # re-analyze allowed
    ClipStatus.FAILED: frozenset(
        {
            ClipStatus.ANALYZED,
            ClipStatus.RENDERED,
            ClipStatus.APPROVED,
            ClipStatus.SCHEDULED,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class VideoTransition:
    from_status: VideoStatus
    to_status: VideoStatus


@dataclass(frozen=True, slots=True)
class ClipTransition:
    from_status: ClipStatus
    to_status: ClipStatus


def can_transition_video(current: VideoStatus, target: VideoStatus) -> bool:
    """Return True if the video transition is allowed (or is a no-op)."""
    if current == target:
        return True  # idempotent
    return target in VIDEO_TRANSITIONS.get(current, frozenset())


def can_transition_clip(current: ClipStatus, target: ClipStatus) -> bool:
    """Return True if the clip transition is allowed (or is a no-op)."""
    if current == target:
        return True
    return target in CLIP_TRANSITIONS.get(current, frozenset())


def apply_video_transition(current: VideoStatus, target: VideoStatus) -> VideoStatus:
    """Validate and return the new video status (idempotent)."""
    if current == target:
        return current
    if not can_transition_video(current, target):
        msg = f"Invalid video transition: {current} → {target}"
        raise InvalidTransitionError(msg)
    return target


def apply_clip_transition(current: ClipStatus, target: ClipStatus) -> ClipStatus:
    """Validate and return the new clip status (idempotent)."""
    if current == target:
        return current
    if not can_transition_clip(current, target):
        msg = f"Invalid clip transition: {current} → {target}"
        raise InvalidTransitionError(msg)
    return target


def next_video_step(status: VideoStatus) -> VideoStatus | None:
    """Return the happy-path next status, or None if terminal."""
    mapping = {
        VideoStatus.DISCOVERED: VideoStatus.DOWNLOADED,
        VideoStatus.DOWNLOADED: VideoStatus.TRANSCRIBED,
        VideoStatus.TRANSCRIBED: VideoStatus.ANALYZED,
    }
    return mapping.get(status)


def next_clip_step(status: ClipStatus, *, require_review: bool) -> ClipStatus | None:
    """Return the happy-path next clip status."""
    if status == ClipStatus.ANALYZED:
        return ClipStatus.RENDERED
    if status == ClipStatus.RENDERED:
        return ClipStatus.AWAITING_REVIEW if require_review else ClipStatus.APPROVED
    if status == ClipStatus.AWAITING_REVIEW:
        return None  # waits for human
    if status == ClipStatus.APPROVED:
        return ClipStatus.SCHEDULED
    if status == ClipStatus.SCHEDULED:
        return ClipStatus.PUBLISHED
    return None
