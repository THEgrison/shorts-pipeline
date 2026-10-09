"""Basic Prometheus metrics for the pipeline."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

PIPELINE_INFO = Info("shorts_pipeline", "Shorts pipeline build info")
PIPELINE_INFO.info({"version": "0.1.0"})

JOBS_TOTAL = Counter(
    "shorts_jobs_total",
    "Total jobs processed by agent",
    ["agent", "status"],
)

JOB_DURATION_SECONDS = Histogram(
    "shorts_job_duration_seconds",
    "Job duration in seconds",
    ["agent"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)

VIDEOS_BY_STATUS = Gauge(
    "shorts_videos_by_status",
    "Count of source videos by status",
    ["status"],
)

CLIPS_BY_STATUS = Gauge(
    "shorts_clips_by_status",
    "Count of clips by status",
    ["status"],
)

PUBLICATIONS_TOTAL = Counter(
    "shorts_publications_total",
    "Total publications",
    ["platform", "status"],
)

YOUTUBE_QUOTA_REMAINING = Gauge(
    "shorts_youtube_quota_remaining",
    "Estimated YouTube Data API quota remaining for the day",
)

ACTIVE_WORKERS = Gauge(
    "shorts_active_workers",
    "Active Celery workers by queue",
    ["queue"],
)
