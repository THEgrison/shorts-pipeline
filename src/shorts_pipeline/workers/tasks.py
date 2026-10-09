"""Celery tasks wiring agents through the Orchestrator."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from shorts_pipeline.db.enums import AgentName
from shorts_pipeline.db.session import get_sync_session
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.orchestrator.alerts import send_alert
from shorts_pipeline.orchestrator.pause import is_agent_paused
from shorts_pipeline.orchestrator.service import Orchestrator

logger = get_logger(__name__)


@shared_task(
    name="shorts_pipeline.workers.tasks.discovery.run_discovery",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def run_discovery(self: Any, niches: list[str] | None = None) -> dict[str, Any]:
    """Celery task: Discovery Agent."""
    if is_agent_paused(AgentName.DISCOVERY):
        logger.info("task.skipped_paused", agent="discovery")
        return {"success": False, "paused": True}
    with get_sync_session() as session:
        orch = Orchestrator(session)
        return orch.run_discovery(niches=niches, celery_task_id=self.request.id)


@shared_task(
    name="shorts_pipeline.workers.tasks.analysis.run_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_analysis(self: Any, source_video_id: int) -> dict[str, Any]:
    """Celery task: Analysis Agent."""
    if is_agent_paused(AgentName.ANALYSIS):
        return {"success": False, "paused": True}
    try:
        with get_sync_session() as session:
            orch = Orchestrator(session)
            return orch.run_analysis(source_video_id, celery_task_id=self.request.id)
    except Exception as exc:
        logger.exception("task.analysis_failed", source_video_id=source_video_id)
        if self.request.retries >= (self.max_retries or 3):
            send_alert(f"Analysis dead-letter for video {source_video_id}: {exc}")
        raise self.retry(exc=exc) from exc


@shared_task(
    name="shorts_pipeline.workers.tasks.editing.run_editing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_editing(self: Any, clip_id: int) -> dict[str, Any]:
    """Celery task: Editing Agent."""
    if is_agent_paused(AgentName.EDITING):
        return {"success": False, "paused": True}
    try:
        with get_sync_session() as session:
            orch = Orchestrator(session)
            return orch.run_editing(clip_id, celery_task_id=self.request.id)
    except Exception as exc:
        logger.exception("task.editing_failed", clip_id=clip_id)
        if self.request.retries >= (self.max_retries or 3):
            send_alert(f"Editing dead-letter for clip {clip_id}: {exc}")
        raise self.retry(exc=exc) from exc


@shared_task(
    name="shorts_pipeline.workers.tasks.publishing.run_publishing",
    bind=True,
    max_retries=5,
    default_retry_delay=120,
)
def run_publishing(self: Any, render_id: int) -> dict[str, Any]:
    """Celery task: Publishing Agent."""
    if is_agent_paused(AgentName.PUBLISHING):
        return {"success": False, "paused": True}
    try:
        with get_sync_session() as session:
            orch = Orchestrator(session)
            return orch.run_publishing(render_id, celery_task_id=self.request.id)
    except Exception as exc:
        logger.exception("task.publishing_failed", render_id=render_id)
        if self.request.retries >= (self.max_retries or 5):
            send_alert(f"Publishing dead-letter for render {render_id}: {exc}")
        raise self.retry(exc=exc) from exc


@shared_task(
    name="shorts_pipeline.workers.tasks.orchestrator.advance_pipeline",
    bind=True,
)
def advance_pipeline(self: Any) -> dict[str, Any]:
    """Celery task: advance all pending entities one step."""
    if is_agent_paused(AgentName.ORCHESTRATOR):
        return {"success": False, "paused": True}
    with get_sync_session() as session:
        orch = Orchestrator(session)
        summary = orch.advance_pending()
        logger.info(
            "orchestrator.advance", task_id=self.request.id, summary_keys=list(summary.keys())
        )
        return {"success": True, "summary": summary}


@shared_task(name="shorts_pipeline.workers.tasks.orchestrator.run_full_dummy_pipeline")
def run_full_dummy_pipeline(niches: list[str] | None = None) -> dict[str, Any]:
    """End-to-end dummy pipeline for smoke tests (discovery → publish)."""
    from shorts_pipeline.db.models import Clip

    with get_sync_session() as session:
        orch = Orchestrator(session)
        disc = orch.run_discovery(niches=niches or ["tech_fr"])
        results: dict[str, Any] = {"discovery": disc}
        for video_id in disc.get("created_ids", []):
            analysis = orch.run_analysis(video_id)
            results.setdefault("analysis", []).append(analysis)
            for clip_id in analysis.get("clip_ids", []):
                edit = orch.run_editing(clip_id)
                results.setdefault("editing", []).append(edit)
                clip = orch.session.get(Clip, clip_id)
                if clip and clip.status.value == "awaiting_review":
                    orch.approve_clip(clip_id)
                if edit.get("render_id"):
                    pub = orch.run_publishing(edit["render_id"])
                    results.setdefault("publishing", []).append(pub)
        return results
