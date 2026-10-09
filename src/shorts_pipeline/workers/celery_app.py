"""Celery application — queues per agent (fleshed out in Phase 2)."""

from __future__ import annotations

from celery import Celery

from shorts_pipeline.config import get_settings

settings = get_settings()

celery_app = Celery(
    "shorts_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "shorts_pipeline.workers.tasks.discovery.*": {"queue": "discovery"},
        "shorts_pipeline.workers.tasks.analysis.*": {"queue": "analysis"},
        "shorts_pipeline.workers.tasks.editing.*": {"queue": "editing"},
        "shorts_pipeline.workers.tasks.publishing.*": {"queue": "publishing"},
        "shorts_pipeline.workers.tasks.orchestrator.*": {"queue": "orchestrator"},
    },
    task_default_queue="orchestrator",
)

# Autodiscover tasks once packages exist (Phase 2+)
celery_app.autodiscover_tasks(
    packages=[
        "shorts_pipeline.workers",
    ],
    related_name="tasks",
)
