"""Persist analysis results into transcripts + clips tables."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shorts_pipeline.agents.analysis.agent import AnalysisOutput
from shorts_pipeline.db.enums import ClipStatus
from shorts_pipeline.db.models import Clip, Transcript
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def persist_analysis(session: Session, result: AnalysisOutput) -> list[int]:
    """Upsert transcript and create clips. Returns clip ids."""
    existing_t = (
        session.query(Transcript).filter_by(source_video_id=result.source_video_id).one_or_none()
    )
    td = result.transcript or {}
    if existing_t is None:
        transcript = Transcript(
            source_video_id=result.source_video_id,
            language=td.get("language"),
            full_text=td.get("full_text") or "",
            words=td.get("words") or [],
            segments=td.get("segments"),
            whisper_model=td.get("whisper_model"),
            duration_sec=td.get("duration_sec"),
            storage_key=result.audio_key,
        )
        session.add(transcript)
    else:
        existing_t.language = td.get("language")
        existing_t.full_text = td.get("full_text") or existing_t.full_text
        existing_t.words = td.get("words") or existing_t.words
        existing_t.segments = td.get("segments")
        existing_t.whisper_model = td.get("whisper_model")
        existing_t.duration_sec = td.get("duration_sec")
        if result.audio_key:
            existing_t.storage_key = result.audio_key

    # If clips already exist for this video, return them (idempotent)
    existing_clips = session.query(Clip).filter_by(source_video_id=result.source_video_id).all()
    if existing_clips:
        return [c.id for c in existing_clips]

    clip_ids: list[int] = []
    for item in result.clips:
        clip = Clip(
            source_video_id=result.source_video_id,
            start_sec=item.start_sec,
            end_sec=item.end_sec,
            score=item.score,
            hook=item.hook,
            reason=item.reason,
            suggested_title=item.suggested_title,
            suggested_hashtags=item.suggested_hashtags,
            status=ClipStatus.ANALYZED,
            rank=item.rank,
            signals=item.signals,
        )
        session.add(clip)
        session.flush()
        clip_ids.append(clip.id)
        logger.info(
            "analysis.clip_persisted",
            clip_id=clip.id,
            score=clip.score,
            start=clip.start_sec,
            end=clip.end_sec,
        )
    return clip_ids
