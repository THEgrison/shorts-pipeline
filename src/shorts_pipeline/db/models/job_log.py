"""Job execution log for observability and dead-letter tracking."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from shorts_pipeline.db.base import Base, TimestampMixin
from shorts_pipeline.db.enums import AgentName, JobStatus


class JobLog(Base, TimestampMixin):
    """Record of an orchestrator / agent task execution."""

    __tablename__ = "jobs_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent: Mapped[AgentName] = mapped_column(
        Enum(AgentName, name="agent_name", native_enum=False),
        nullable=False,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    source_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_videos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    clip_id: Mapped[int | None] = mapped_column(
        ForeignKey("clips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    render_id: Mapped[int | None] = mapped_column(
        ForeignKey("renders.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
