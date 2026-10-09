"""State machine transition tests."""

from __future__ import annotations

import pytest

from shorts_pipeline.db.enums import ClipStatus, VideoStatus
from shorts_pipeline.orchestrator.state_machine import (
    InvalidTransitionError,
    apply_clip_transition,
    apply_video_transition,
    can_transition_video,
    next_clip_step,
    next_video_step,
)


def test_video_happy_path() -> None:
    status = VideoStatus.DISCOVERED
    for target in (
        VideoStatus.DOWNLOADED,
        VideoStatus.TRANSCRIBED,
        VideoStatus.ANALYZED,
    ):
        status = apply_video_transition(status, target)
    assert status == VideoStatus.ANALYZED
    assert next_video_step(status) is None


def test_video_idempotent() -> None:
    assert apply_video_transition(VideoStatus.DISCOVERED, VideoStatus.DISCOVERED) == (
        VideoStatus.DISCOVERED
    )


def test_video_invalid() -> None:
    with pytest.raises(InvalidTransitionError):
        apply_video_transition(VideoStatus.DISCOVERED, VideoStatus.ANALYZED)


def test_clip_review_path() -> None:
    assert next_clip_step(ClipStatus.RENDERED, require_review=True) == ClipStatus.AWAITING_REVIEW
    assert next_clip_step(ClipStatus.RENDERED, require_review=False) == ClipStatus.APPROVED
    status = apply_clip_transition(ClipStatus.ANALYZED, ClipStatus.RENDERED)
    status = apply_clip_transition(status, ClipStatus.AWAITING_REVIEW)
    status = apply_clip_transition(status, ClipStatus.APPROVED)
    status = apply_clip_transition(status, ClipStatus.SCHEDULED)
    status = apply_clip_transition(status, ClipStatus.PUBLISHED)
    assert status == ClipStatus.PUBLISHED


def test_can_transition_helpers() -> None:
    assert can_transition_video(VideoStatus.DISCOVERED, VideoStatus.DOWNLOADED)
    assert not can_transition_video(VideoStatus.SKIPPED, VideoStatus.DISCOVERED)
