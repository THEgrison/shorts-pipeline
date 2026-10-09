"""Celery application — queues per agent."""

from __future__ import annotations

from celery import Celery

from shorts_pipeline.config import get_settings

settings = get_settings()

celery_app = Celery(
    "shorts_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["shorts_pipeline.workers.tasks"],
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
    # Beat schedule filled in Phase 8; Phase 2 can trigger advance manually
    beat_schedule={
        "advance-pipeline-every-2-minutes": {
            "task": "shorts_pipeline.workers.tasks.orchestrator.advance_pipeline",
            "schedule": 120.0,
        },
        "cleanup-temp-hourly": {
            "task": "shorts_pipeline.workers.tasks.orchestrator.cleanup_temp",
            "schedule": 3600.0,
            "kwargs": {"max_age_hours": 24.0},
        },
    },
)
