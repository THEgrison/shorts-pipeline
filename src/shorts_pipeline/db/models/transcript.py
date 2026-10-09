"""Word-level transcripts produced by Whisper."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from shorts_pipeline.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shorts_pipeline.db.models.source_video import SourceVideo


class Transcript(Base, TimestampMixin):
    """Full transcript for a source video."""

    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("source_video_id", name="uq_transcripts_source_video_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_video_id: Mapped[int] = mapped_column(
        ForeignKey("source_videos.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    # [{word, start, end, probability}, ...]
    words: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    # [{start, end, text}, ...]
    segments: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    whisper_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    source_video: Mapped[SourceVideo] = relationship(
        "SourceVideo",
        back_populates="transcript",
    )
