"""Persist DiscoveryAgent output into source_videos (idempotent)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shorts_pipeline.agents.discovery.agent import DiscoveredVideo
from shorts_pipeline.db.enums import VideoStatus
from shorts_pipeline.db.models import ChannelWhitelist, SourceVideo
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def load_whitelist_channel_ids(session: Session) -> set[str]:
    rows = session.query(ChannelWhitelist).filter(ChannelWhitelist.is_active.is_(True)).all()
    return {r.youtube_channel_id for r in rows}


def load_seen_video_ids(session: Session) -> set[str]:
    rows = session.query(SourceVideo.youtube_video_id).all()
    return {r[0] for r in rows}


def persist_discovered_videos(
    session: Session,
    videos: list[DiscoveredVideo],
) -> list[int]:
    """Insert new source_videos; skip duplicates. Returns created DB ids."""
    whitelist = {c.youtube_channel_id: c.id for c in session.query(ChannelWhitelist).all()}
    created: list[int] = []
    for item in videos:
        existing = (
            session.query(SourceVideo)
            .filter_by(youtube_video_id=item.youtube_video_id)
            .one_or_none()
        )
        if existing:
            continue
        channel_fk = whitelist.get(item.youtube_channel_id)
        row = SourceVideo(
            youtube_video_id=item.youtube_video_id,
            channel_id=channel_fk,
            youtube_channel_id=item.youtube_channel_id,
            title=item.title,
            description=item.description,
            published_at=item.published_at,
            duration_sec=item.duration_sec,
            view_count=item.view_count,
            like_count=item.like_count,
            comment_count=item.comment_count,
            language=item.language,
            license=item.license,
            license_basis=item.license_basis,
            relevance_score=item.relevance_score,
            status=VideoStatus.DISCOVERED,
            thumbnail_url=item.thumbnail_url,
            raw_metadata=item.raw_metadata,
        )
        session.add(row)
        session.flush()
        created.append(row.id)
        logger.info(
            "discovery.persisted",
            source_video_id=row.id,
            youtube_video_id=item.youtube_video_id,
            license_basis=item.license_basis.value,
            score=item.relevance_score,
        )
    return created
