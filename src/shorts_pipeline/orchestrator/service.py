"""Orchestrator: advance pipeline entities through the state machine."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from shorts_pipeline.agents.analysis.agent import (
    AnalysisAgent,
    AnalysisInput,
    build_test_analysis_agent,
)
from shorts_pipeline.agents.analysis.persist import persist_analysis
from shorts_pipeline.agents.discovery.agent import DiscoveryAgent, DiscoveryInput
from shorts_pipeline.agents.discovery.persist import (
    load_seen_video_ids,
    load_whitelist_channel_ids,
    persist_discovered_videos,
)
from shorts_pipeline.agents.dummy import (
    DummyDiscoveryAgent,
    DummyDiscoveryInput,
    DummyEditingAgent,
    DummyEditingInput,
    DummyPublishingAgent,
    DummyPublishingInput,
)
from shorts_pipeline.clients.youtube import YouTubeClient
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.db.enums import (
    AgentName,
    ClipStatus,
    JobStatus,
    LicenseBasis,
    PublicationStatus,
    RenderStatus,
    VideoStatus,
)
from shorts_pipeline.db.models import Clip, JobLog, Publication, Render, SourceVideo
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.metrics import JOB_DURATION_SECONDS, JOBS_TOTAL
from shorts_pipeline.orchestrator.job_logger import finish_job, start_job
from shorts_pipeline.orchestrator.pause import is_agent_paused
from shorts_pipeline.orchestrator.state_machine import (
    apply_clip_transition,
    apply_video_transition,
    next_clip_step,
    next_video_step,
)

logger = get_logger(__name__)

MAX_ATTEMPTS_BEFORE_DEAD_LETTER = 3


class Orchestrator:
    """Coordinates agent runs and persists state transitions."""

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        discovery_agent: DiscoveryAgent | DummyDiscoveryAgent | None = None,
        analysis_agent: AnalysisAgent | None = None,
        youtube_client: YouTubeClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.youtube_client = youtube_client
        self.discovery: DiscoveryAgent | DummyDiscoveryAgent = (
            discovery_agent or self._build_discovery_agent()
        )
        self.analysis = analysis_agent or self._build_analysis_agent()
        self.editing = DummyEditingAgent()
        self.publishing = DummyPublishingAgent()

    def _build_discovery_agent(self) -> DiscoveryAgent | DummyDiscoveryAgent:
        """Use real DiscoveryAgent when a YouTube API key (or injected client) is available."""
        if self.youtube_client is not None:
            return DiscoveryAgent(self.youtube_client, settings=self.settings)
        key = self.settings.youtube_api_key
        if key is not None and key.get_secret_value():
            client = YouTubeClient(api_key=key.get_secret_value(), settings=self.settings)
            return DiscoveryAgent(client, settings=self.settings)
        logger.warning("discovery.using_dummy_agent_no_youtube_api_key")
        return DummyDiscoveryAgent()

    def _build_analysis_agent(self) -> AnalysisAgent:
        """Prefer real stack when keys exist; otherwise use fake collaborators."""
        has_anthropic = (
            self.settings.anthropic_api_key is not None
            and self.settings.anthropic_api_key.get_secret_value()
        )
        # Tests / local dry-run without Anthropic: fully mocked collaborators
        if self.settings.app_env == "test" or (
            not has_anthropic and self.settings.dry_run
        ):
            return build_test_analysis_agent(settings=self.settings)
        return AnalysisAgent(settings=self.settings)

    # ------------------------------------------------------------------ discovery
    def run_discovery(
        self, *, niches: list[str] | None = None, celery_task_id: str | None = None
    ) -> dict[str, Any]:
        """Run discovery agent and persist newly found videos."""
        if is_agent_paused(AgentName.DISCOVERY):
            return {"success": False, "paused": True, "message": "discovery paused"}

        started = time.perf_counter()
        job = start_job(
            self.session,
            agent=AgentName.DISCOVERY,
            celery_task_id=celery_task_id,
            input_payload={"niches": niches or []},
        )
        try:
            created_ids: list[int]
            meta: dict[str, Any] = {}

            if isinstance(self.discovery, DiscoveryAgent):
                result = self.discovery.run(
                    DiscoveryInput(
                        niches=niches or [],
                        dry_run=self.settings.dry_run,
                        already_seen_ids=load_seen_video_ids(self.session),
                        whitelist_channel_ids=load_whitelist_channel_ids(self.session),
                    )
                )
                created_ids = persist_discovered_videos(self.session, result.videos)
                meta = {
                    "skipped_unauthorized": result.skipped_unauthorized,
                    "skipped_duplicate": result.skipped_duplicate,
                    "skipped_low_score": result.skipped_low_score,
                    "quota_remaining": result.quota_remaining,
                    "kept": len(result.videos),
                }
            else:
                result_dummy = self.discovery.run(
                    DummyDiscoveryInput(niches=niches or [], dry_run=self.settings.dry_run)
                )
                created_ids = []
                for yt_id in result_dummy.video_ids:
                    existing = (
                        self.session.query(SourceVideo)
                        .filter_by(youtube_video_id=yt_id)
                        .one_or_none()
                    )
                    if existing:
                        continue
                    video = SourceVideo(
                        youtube_video_id=yt_id,
                        youtube_channel_id="UC_DUMMY_CHANNEL",
                        title=f"Dummy video {yt_id}",
                        license="creativeCommon",
                        license_basis=LicenseBasis.CREATIVE_COMMONS,
                        status=VideoStatus.DISCOVERED,
                        relevance_score=75.0,
                        duration_sec=1200,
                        language="fr",
                    )
                    self.session.add(video)
                    self.session.flush()
                    created_ids.append(video.id)

            duration = time.perf_counter() - started
            finish_job(
                self.session,
                job,
                status=JobStatus.SUCCESS,
                output_payload={"created_ids": created_ids, **meta},
                duration_sec=duration,
            )
            JOBS_TOTAL.labels(agent="discovery", status="success").inc()
            JOB_DURATION_SECONDS.labels(agent="discovery").observe(duration)
            self.session.commit()
            return {"success": True, "created_ids": created_ids, "job_id": job.id, **meta}
        except Exception as exc:
            self.session.rollback()
            self._fail_job(job, exc, agent="discovery", started=started)
            raise

    # ------------------------------------------------------------------ analysis
    def run_analysis(
        self, source_video_id: int, *, celery_task_id: str | None = None
    ) -> dict[str, Any]:
        """Download→transcribe→analyze path (dummy): creates a clip and marks analyzed."""
        if is_agent_paused(AgentName.ANALYSIS):
            return {"success": False, "paused": True, "message": "analysis paused"}

        video = self.session.get(SourceVideo, source_video_id)
        if video is None:
            msg = f"SourceVideo {source_video_id} not found"
            raise ValueError(msg)

        started = time.perf_counter()
        job = start_job(
            self.session,
            agent=AgentName.ANALYSIS,
            celery_task_id=celery_task_id,
            source_video_id=source_video_id,
            input_payload={"source_video_id": source_video_id},
            attempt=video.attempt_count + 1,
        )
        try:
            # Idempotent: skip if already analyzed with clips
            if video.status == VideoStatus.ANALYZED and video.clips:
                finish_job(
                    self.session,
                    job,
                    status=JobStatus.SUCCESS,
                    output_payload={"idempotent": True, "clip_ids": [c.id for c in video.clips]},
                    duration_sec=time.perf_counter() - started,
                )
                self.session.commit()
                return {
                    "success": True,
                    "idempotent": True,
                    "clip_ids": [c.id for c in video.clips],
                }

            # Advance through intermediate statuses (download + transcribe)
            for target in (VideoStatus.DOWNLOADED, VideoStatus.TRANSCRIBED):
                if video.status != target and video.status != VideoStatus.ANALYZED:
                    video.status = apply_video_transition(video.status, target)
                    self.session.flush()

            result = self.analysis.run(
                AnalysisInput(
                    source_video_id=video.id,
                    youtube_video_id=video.youtube_video_id,
                    dry_run=self.settings.dry_run,
                )
            )
            if result.storage_key:
                video.storage_key = result.storage_key

            clip_ids = persist_analysis(self.session, result)
            self.session.flush()

            video.status = apply_video_transition(video.status, VideoStatus.ANALYZED)
            video.attempt_count = 0
            video.error_message = None
            duration = time.perf_counter() - started
            finish_job(
                self.session,
                job,
                status=JobStatus.SUCCESS,
                output_payload={"clip_ids": clip_ids},
                duration_sec=duration,
            )
            JOBS_TOTAL.labels(agent="analysis", status="success").inc()
            JOB_DURATION_SECONDS.labels(agent="analysis").observe(duration)
            self.session.commit()
            return {"success": True, "clip_ids": clip_ids, "job_id": job.id}
        except Exception as exc:
            video.attempt_count += 1
            video.status = apply_video_transition(video.status, VideoStatus.FAILED)
            video.error_message = str(exc)
            self.session.commit()
            self._fail_job(
                job,
                exc,
                agent="analysis",
                started=started,
                dead_letter=video.attempt_count >= MAX_ATTEMPTS_BEFORE_DEAD_LETTER,
            )
            raise

    # ------------------------------------------------------------------ editing
    def run_editing(self, clip_id: int, *, celery_task_id: str | None = None) -> dict[str, Any]:
        """Render a clip (dummy) and optionally move to review/approved."""
        if is_agent_paused(AgentName.EDITING):
            return {"success": False, "paused": True, "message": "editing paused"}

        clip = self.session.get(Clip, clip_id)
        if clip is None:
            msg = f"Clip {clip_id} not found"
            raise ValueError(msg)

        started = time.perf_counter()
        job = start_job(
            self.session,
            agent=AgentName.EDITING,
            celery_task_id=celery_task_id,
            clip_id=clip_id,
            source_video_id=clip.source_video_id,
            input_payload={"clip_id": clip_id},
        )
        try:
            existing = (
                self.session.query(Render)
                .filter_by(clip_id=clip_id, status=RenderStatus.RENDERED)
                .first()
            )
            if existing and clip.status in {
                ClipStatus.RENDERED,
                ClipStatus.AWAITING_REVIEW,
                ClipStatus.APPROVED,
                ClipStatus.SCHEDULED,
                ClipStatus.PUBLISHED,
            }:
                finish_job(
                    self.session,
                    job,
                    status=JobStatus.SUCCESS,
                    output_payload={"idempotent": True, "render_id": existing.id},
                    duration_sec=time.perf_counter() - started,
                )
                self.session.commit()
                return {"success": True, "idempotent": True, "render_id": existing.id}

            result = self.editing.run(
                DummyEditingInput(clip_id=clip_id, dry_run=self.settings.dry_run)
            )
            render = Render(
                clip_id=clip_id,
                status=RenderStatus.RENDERED,
                storage_key=result.storage_key,
                thumbnail_key=f"thumbnails/dummy_clip_{clip_id}.jpg",
                style_template_name=self.settings.editing_default_style_template,
                duration_sec=clip.end_sec - clip.start_sec,
                title=clip.suggested_title,
                description=clip.reason,
            )
            self.session.add(render)
            self.session.flush()

            clip.status = apply_clip_transition(clip.status, ClipStatus.RENDERED)
            next_status = next_clip_step(clip.status, require_review=self.settings.require_review)
            if next_status is not None:
                clip.status = apply_clip_transition(clip.status, next_status)

            duration = time.perf_counter() - started
            finish_job(
                self.session,
                job,
                status=JobStatus.SUCCESS,
                output_payload={"render_id": render.id, "clip_status": clip.status.value},
                duration_sec=duration,
            )
            JOBS_TOTAL.labels(agent="editing", status="success").inc()
            JOB_DURATION_SECONDS.labels(agent="editing").observe(duration)
            self.session.commit()
            return {
                "success": True,
                "render_id": render.id,
                "clip_status": clip.status.value,
                "job_id": job.id,
            }
        except Exception as exc:
            clip.status = apply_clip_transition(clip.status, ClipStatus.FAILED)
            clip.error_message = str(exc)
            self.session.commit()
            self._fail_job(job, exc, agent="editing", started=started)
            raise

    # ------------------------------------------------------------------ publishing
    def run_publishing(
        self, render_id: int, *, celery_task_id: str | None = None
    ) -> dict[str, Any]:
        """Publish a render (dry-run by default)."""
        if is_agent_paused(AgentName.PUBLISHING):
            return {"success": False, "paused": True, "message": "publishing paused"}

        render = self.session.get(Render, render_id)
        if render is None:
            msg = f"Render {render_id} not found"
            raise ValueError(msg)
        clip = render.clip
        idempotency_key = f"render-{render_id}-dummy"

        # Idempotent: already published
        existing_pub = (
            self.session.query(Publication)
            .filter_by(render_id=render_id, idempotency_key=idempotency_key)
            .one_or_none()
        )
        if existing_pub and existing_pub.status in {
            PublicationStatus.PUBLISHED,
            PublicationStatus.DRY_RUN,
        }:
            return {
                "success": True,
                "idempotent": True,
                "publication_id": existing_pub.id,
            }
        if clip.status == ClipStatus.PUBLISHED:
            return {"success": True, "idempotent": True, "message": "clip already published"}

        # Human-in-the-loop gate
        if clip.status == ClipStatus.AWAITING_REVIEW:
            return {
                "success": False,
                "awaiting_review": True,
                "message": "clip awaiting human review",
            }
        if clip.status not in {ClipStatus.APPROVED, ClipStatus.SCHEDULED}:
            # Auto-approve path when review disabled and still rendered
            if clip.status == ClipStatus.RENDERED and not self.settings.require_review:
                clip.status = apply_clip_transition(clip.status, ClipStatus.APPROVED)
            else:
                return {
                    "success": False,
                    "message": f"clip status {clip.status} not publishable",
                }

        started = time.perf_counter()
        job = start_job(
            self.session,
            agent=AgentName.PUBLISHING,
            celery_task_id=celery_task_id,
            clip_id=clip.id,
            render_id=render_id,
            input_payload={"render_id": render_id},
        )
        try:
            clip.status = apply_clip_transition(clip.status, ClipStatus.SCHEDULED)
            result = self.publishing.run(
                DummyPublishingInput(
                    render_id=render_id,
                    dry_run=self.settings.dry_run,
                )
            )

            pub_status = (
                PublicationStatus.DRY_RUN if self.settings.dry_run else PublicationStatus.PUBLISHED
            )
            from shorts_pipeline.db.enums import Platform

            publication = Publication(
                render_id=render_id,
                account_id=self._ensure_dummy_account(),
                platform=Platform.YOUTUBE_SHORTS,
                status=pub_status,
                title=render.title,
                description=render.description,
                external_url=result.external_url,
                idempotency_key=idempotency_key,
                attempt_count=1,
            )
            self.session.add(publication)
            clip.status = apply_clip_transition(clip.status, ClipStatus.PUBLISHED)
            duration = time.perf_counter() - started
            finish_job(
                self.session,
                job,
                status=JobStatus.SUCCESS,
                output_payload={
                    "publication_status": pub_status.value,
                    "external_url": result.external_url,
                },
                duration_sec=duration,
            )
            JOBS_TOTAL.labels(agent="publishing", status="success").inc()
            JOB_DURATION_SECONDS.labels(agent="publishing").observe(duration)
            self.session.commit()
            return {
                "success": True,
                "publication_status": pub_status.value,
                "external_url": result.external_url,
                "job_id": job.id,
            }
        except Exception as exc:
            clip.status = apply_clip_transition(clip.status, ClipStatus.FAILED)
            clip.error_message = str(exc)
            self.session.commit()
            self._fail_job(job, exc, agent="publishing", started=started)
            raise

    # ------------------------------------------------------------------ tick / advance
    def advance_pending(self) -> dict[str, Any]:
        """Process one batch of pending work (used by orchestrator Celery beat/task)."""
        summary: dict[str, Any] = {"videos": [], "clips": [], "renders": []}

        videos = (
            self.session.query(SourceVideo)
            .filter(
                SourceVideo.status.in_(
                    [VideoStatus.DISCOVERED, VideoStatus.DOWNLOADED, VideoStatus.TRANSCRIBED]
                )
            )
            .limit(10)
            .all()
        )
        for video in videos:
            nxt = next_video_step(video.status)
            if nxt is None:
                continue
            # For dummy pipeline, jump to full analysis from discovered
            summary["videos"].append(self.run_analysis(video.id))

        clips = self.session.query(Clip).filter(Clip.status == ClipStatus.ANALYZED).limit(10).all()
        for clip in clips:
            summary["clips"].append(self.run_editing(clip.id))

        # Auto-publish approved (or skip review when disabled)
        publishable = (
            self.session.query(Clip)
            .filter(Clip.status.in_([ClipStatus.APPROVED, ClipStatus.SCHEDULED]))
            .limit(10)
            .all()
        )
        for clip in publishable:
            render = (
                self.session.query(Render)
                .filter_by(clip_id=clip.id, status=RenderStatus.RENDERED)
                .order_by(Render.id.desc())
                .first()
            )
            if render:
                summary["renders"].append(self.run_publishing(render.id))

        return summary

    def approve_clip(self, clip_id: int) -> Clip:
        """Human-in-the-loop: approve a clip awaiting review."""
        clip = self.session.get(Clip, clip_id)
        if clip is None:
            msg = f"Clip {clip_id} not found"
            raise ValueError(msg)
        clip.status = apply_clip_transition(clip.status, ClipStatus.APPROVED)
        self.session.commit()
        return clip

    def reject_clip(self, clip_id: int, *, notes: str | None = None) -> Clip:
        """Human-in-the-loop: reject a clip."""
        clip = self.session.get(Clip, clip_id)
        if clip is None:
            msg = f"Clip {clip_id} not found"
            raise ValueError(msg)
        clip.status = apply_clip_transition(clip.status, ClipStatus.REJECTED)
        clip.review_notes = notes
        self.session.commit()
        return clip

    # ------------------------------------------------------------------ helpers
    def _ensure_dummy_account(self) -> int:
        from shorts_pipeline.db.enums import Platform
        from shorts_pipeline.db.models import Account

        account = (
            self.session.query(Account)
            .filter_by(platform=Platform.YOUTUBE_SHORTS, external_account_id="dummy-yt")
            .one_or_none()
        )
        if account:
            return account.id
        account = Account(
            platform=Platform.YOUTUBE_SHORTS,
            display_name="Dummy YouTube",
            external_account_id="dummy-yt",
            is_active=True,
        )
        self.session.add(account)
        self.session.flush()
        return account.id

    def _fail_job(
        self,
        job: JobLog,
        exc: Exception,
        *,
        agent: str,
        started: float,
        dead_letter: bool = False,
    ) -> None:
        status = JobStatus.DEAD_LETTER if dead_letter else JobStatus.FAILED
        try:
            # Re-bind job in a fresh transaction if needed
            if job not in self.session:
                job = self.session.merge(job)
            finish_job(
                self.session,
                job,
                status=status,
                error_message=str(exc),
                duration_sec=time.perf_counter() - started,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("job.fail_persist_error", job_id=getattr(job, "id", None))
        JOBS_TOTAL.labels(agent=agent, status=status.value).inc()
        logger.error("job.failed", agent=agent, error=str(exc), dead_letter=dead_letter)


def new_idempotency_key() -> str:
    return uuid.uuid4().hex
