"""Discovered YouTube source videos."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from shorts_pipeline.db.base import Base, TimestampMixin
from shorts_pipeline.db.enums import LicenseBasis, VideoStatus

if TYPE_CHECKING:
    from shorts_pipeline.db.models.channel import ChannelWhitelist
    from shorts_pipeline.db.models.clip import Clip
    from shorts_pipeline.db.models.transcript import Transcript


class SourceVideo(Base, TimestampMixin):
    """A YouTube video discovered and authorized for processing."""

    __tablename__ = "source_videos"
    __table_args__ = (
        UniqueConstraint("youtube_video_id", name="uq_source_videos_youtube_video_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    youtube_video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels_whitelist.id", ondelete="SET NULL"),
        nullable=True,
    )
    youtube_channel_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_basis: Mapped[LicenseBasis] = mapped_column(
        Enum(LicenseBasis, name="license_basis", native_enum=False),
        nullable=False,
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status", native_enum=False),
        default=VideoStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    channel: Mapped[ChannelWhitelist | None] = relationship(
        "ChannelWhitelist",
        back_populates="source_videos",
    )
    transcript: Mapped[Transcript | None] = relationship(
        "Transcript",
        back_populates="source_video",
        uselist=False,
    )
    clips: Mapped[list[Clip]] = relationship(
        "Clip",
        back_populates="source_video",
    )
