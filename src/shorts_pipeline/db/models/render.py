"""Rendered short video files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shorts_pipeline.db.base import Base, TimestampMixin
from shorts_pipeline.db.enums import RenderStatus

if TYPE_CHECKING:
    from shorts_pipeline.db.models.clip import Clip
    from shorts_pipeline.db.models.publication import Publication


class Render(Base, TimestampMixin):
    """An exported 9:16 short ready (or being prepared) for publishing."""

    __tablename__ = "renders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clip_id: Mapped[int] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[RenderStatus] = mapped_column(
        Enum(RenderStatus, name="render_status", native_enum=False),
        default=RenderStatus.PENDING,
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subtitle_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    style_template_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1920, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    clip: Mapped[Clip] = relationship("Clip", back_populates="renders")
    publications: Mapped[list[Publication]] = relationship(
        "Publication",
        back_populates="render",
    )
