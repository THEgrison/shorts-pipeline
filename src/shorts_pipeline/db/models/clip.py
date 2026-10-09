"""Analyzed clip moments within a source video."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from shorts_pipeline.db.base import Base, TimestampMixin
from shorts_pipeline.db.enums import ClipStatus

if TYPE_CHECKING:
    from shorts_pipeline.db.models.render import Render
    from shorts_pipeline.db.models.source_video import SourceVideo


class Clip(Base, TimestampMixin):
    """A high-potential short segment detected by the Analysis Agent."""

    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_video_id: Mapped[int] = mapped_column(
        ForeignKey("source_videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    hook: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    suggested_hashtags: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    status: Mapped[ClipStatus] = mapped_column(
        Enum(ClipStatus, name="clip_status", native_enum=False),
        default=ClipStatus.ANALYZED,
        nullable=False,
        index=True,
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signals: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_video: Mapped[SourceVideo] = relationship(
        "SourceVideo",
        back_populates="clips",
    )
    renders: Mapped[list[Render]] = relationship(
        "Render",
        back_populates="clip",
    )
