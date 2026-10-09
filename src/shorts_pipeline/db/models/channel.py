"""Whitelisted YouTube channels (owned / authorized)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shorts_pipeline.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shorts_pipeline.db.models.source_video import SourceVideo


class ChannelWhitelist(Base, TimestampMixin):
    """Channels the pipeline is authorized to process."""

    __tablename__ = "channels_whitelist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_owned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    source_videos: Mapped[list[SourceVideo]] = relationship(
        "SourceVideo",
        back_populates="channel",
    )
