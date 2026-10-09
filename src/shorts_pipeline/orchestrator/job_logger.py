"""Persist job execution records to jobs_log."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from shorts_pipeline.db.enums import AgentName, JobStatus
from shorts_pipeline.db.models import JobLog
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def start_job(
    session: Session,
    *,
    agent: AgentName,
    celery_task_id: str | None = None,
    source_video_id: int | None = None,
    clip_id: int | None = None,
    render_id: int | None = None,
    input_payload: dict[str, Any] | None = None,
    attempt: int = 1,
) -> JobLog:
    """Create a RUNNING job log entry."""
    job = JobLog(
        agent=agent,
        status=JobStatus.RUNNING,
        celery_task_id=celery_task_id,
        source_video_id=source_video_id,
        clip_id=clip_id,
        render_id=render_id,
        input_payload=input_payload,
        attempt=attempt,
    )
    session.add(job)
    session.flush()
    logger.info(
        "job.started",
        job_id=job.id,
        agent=agent.value,
        celery_task_id=celery_task_id,
    )
    return job


def finish_job(
    session: Session,
    job: JobLog,
    *,
    status: JobStatus,
    output_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
    duration_sec: float | None = None,
) -> JobLog:
    """Update job log with terminal (or retrying/dead-letter) status."""
    job.status = status
    job.output_payload = output_payload
    job.error_message = error_message
    job.duration_sec = duration_sec
    session.flush()
    logger.info(
        "job.finished",
        job_id=job.id,
        agent=job.agent.value,
        status=status.value,
        duration_sec=duration_sec,
    )
    return job
