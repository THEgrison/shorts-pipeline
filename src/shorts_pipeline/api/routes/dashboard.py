"""HTMX control dashboard routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from shorts_pipeline.config import get_settings
from shorts_pipeline.db.enums import (
    AgentName,
    ClipStatus,
    JobStatus,
    PublicationStatus,
    VideoStatus,
)
from shorts_pipeline.db.models import (
    Account,
    ChannelWhitelist,
    Clip,
    JobLog,
    Publication,
    Render,
    SourceVideo,
)
from shorts_pipeline.db.session import get_sync_session
from shorts_pipeline.orchestrator.pause import is_agent_paused, pause_agent, resume_agent
from shorts_pipeline.orchestrator.service import Orchestrator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _stats() -> dict[str, int]:
    empty = {"videos": 0, "clips": 0, "renders": 0, "published": 0, "failed": 0, "awaiting": 0}
    try:
        with get_sync_session() as session:
            return {
                "videos": session.query(func.count(SourceVideo.id)).scalar() or 0,
                "clips": session.query(func.count(Clip.id)).scalar() or 0,
                "renders": session.query(func.count(Render.id)).scalar() or 0,
                "published": session.query(func.count(Publication.id))
                .filter(
                    Publication.status.in_([PublicationStatus.PUBLISHED, PublicationStatus.DRY_RUN])
                )
                .scalar()
                or 0,
                "failed": session.query(func.count(JobLog.id))
                .filter(JobLog.status.in_([JobStatus.FAILED, JobStatus.DEAD_LETTER]))
                .scalar()
                or 0,
                "awaiting": session.query(func.count(Clip.id))
                .filter(Clip.status == ClipStatus.AWAITING_REVIEW)
                .scalar()
                or 0,
            }
    except Exception:
        return empty


def _quota_remaining() -> int | str:
    try:
        # Gauge may be unset; fall back to settings limit
        settings = get_settings()
        return settings.youtube_quota_daily_limit
    except Exception:
        return "?"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request) -> HTMLResponse:
    settings = get_settings()
    agents = [(a.value, is_agent_paused(a)) for a in AgentName if a != AgentName.CLEANUP]
    return templates.TemplateResponse(
        request,
        "dashboard_home.html",
        {
            "nav": "home",
            "stats": _stats(),
            "dry_run": settings.dry_run,
            "require_review": settings.require_review,
            "quota_remaining": _quota_remaining(),
            "agents": agents,
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/videos", response_class=HTMLResponse)
async def list_videos(request: Request, status: str | None = None) -> HTMLResponse:
    videos: list[Any] = []
    try:
        with get_sync_session() as session:
            q = session.query(SourceVideo).order_by(SourceVideo.id.desc())
            if status:
                q = q.filter(SourceVideo.status == status)
            videos = q.limit(100).all()
    except Exception:
        videos = []
    return templates.TemplateResponse(
        request,
        "videos.html",
        {
            "nav": "videos",
            "videos": videos,
            "status": status or "",
            "statuses": [s.value for s in VideoStatus],
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/clips", response_class=HTMLResponse)
async def list_clips(request: Request, status: str | None = None) -> HTMLResponse:
    clips: list[Any] = []
    try:
        with get_sync_session() as session:
            q = session.query(Clip).order_by(Clip.id.desc())
            if status:
                q = q.filter(Clip.status == status)
            clips = q.limit(100).all()
    except Exception:
        clips = []
    return templates.TemplateResponse(
        request,
        "clips.html",
        {
            "nav": "clips",
            "clips": clips,
            "status": status or "",
            "statuses": [s.value for s in ClipStatus],
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/renders", response_class=HTMLResponse)
async def list_renders(request: Request) -> HTMLResponse:
    renders: list[Any] = []
    try:
        with get_sync_session() as session:
            renders = session.query(Render).order_by(Render.id.desc()).limit(100).all()
    except Exception:
        renders = []
    return templates.TemplateResponse(
        request,
        "renders.html",
        {"nav": "renders", "renders": renders, "flash": request.query_params.get("flash")},
    )


@router.get("/publications", response_class=HTMLResponse)
async def list_publications(request: Request) -> HTMLResponse:
    publications: list[Any] = []
    try:
        with get_sync_session() as session:
            publications = (
                session.query(Publication).order_by(Publication.id.desc()).limit(100).all()
            )
    except Exception:
        publications = []
    return templates.TemplateResponse(
        request,
        "publications.html",
        {
            "nav": "publications",
            "publications": publications,
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request) -> HTMLResponse:
    settings = get_settings()
    channels: list[Any] = []
    accounts: list[Any] = []
    niches_path = Path("config/niches.yaml")
    niches_preview = (
        niches_path.read_text(encoding="utf-8") if niches_path.exists() else "(missing)"
    )
    try:
        with get_sync_session() as session:
            channels = session.query(ChannelWhitelist).all()
            accounts = session.query(Account).all()
    except Exception:
        pass
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "nav": "config",
            "settings": settings,
            "channels": channels,
            "accounts": accounts,
            "niches_preview": niches_preview,
        },
    )


# --- actions ---


@router.post("/actions/discovery")
async def action_discovery() -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).run_discovery()
        msg = "Discovery lancé"
    except Exception as exc:
        msg = f"Discovery erreur: {exc}"
    return RedirectResponse(f"/dashboard?flash={msg}", status_code=303)


@router.post("/actions/advance")
async def action_advance() -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).advance_pending()
        msg = "Pipeline avancé"
    except Exception as exc:
        msg = f"Advance erreur: {exc}"
    return RedirectResponse(f"/dashboard?flash={msg}", status_code=303)


@router.post("/actions/dummy-e2e")
async def action_dummy_e2e() -> RedirectResponse:
    from shorts_pipeline.workers.tasks import run_full_dummy_pipeline

    try:
        run_full_dummy_pipeline()
        msg = "Dummy E2E OK"
    except Exception as exc:
        msg = f"E2E erreur: {exc}"
    return RedirectResponse(f"/dashboard?flash={msg}", status_code=303)


@router.post("/videos/{video_id}/analyze")
async def action_analyze(video_id: int) -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).run_analysis(video_id)
        msg = f"Analyse vidéo {video_id} OK"
    except Exception as exc:
        msg = f"Analyse erreur: {exc}"
    return RedirectResponse(f"/dashboard/videos?flash={msg}", status_code=303)


@router.post("/clips/{clip_id}/edit")
async def action_edit(clip_id: int) -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).run_editing(clip_id)
        msg = f"Rendu clip {clip_id} OK"
    except Exception as exc:
        msg = f"Rendu erreur: {exc}"
    return RedirectResponse(f"/dashboard/clips?flash={msg}", status_code=303)


@router.post("/clips/{clip_id}/approve")
async def action_approve(clip_id: int) -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).approve_clip(clip_id)
        msg = f"Clip {clip_id} approuvé"
    except Exception as exc:
        msg = f"Approve erreur: {exc}"
    return RedirectResponse(f"/dashboard/clips?flash={msg}", status_code=303)


@router.post("/clips/{clip_id}/reject")
async def action_reject(clip_id: int) -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).reject_clip(clip_id, notes="rejected via dashboard")
        msg = f"Clip {clip_id} rejeté"
    except Exception as exc:
        msg = f"Reject erreur: {exc}"
    return RedirectResponse(f"/dashboard/clips?flash={msg}", status_code=303)


@router.post("/clips/{clip_id}/meta")
async def action_clip_meta(
    clip_id: int,
    title: str = Form(""),
    description: str = Form(""),
) -> RedirectResponse:
    try:
        with get_sync_session() as session:
            clip = session.get(Clip, clip_id)
            if clip:
                clip.suggested_title = title or clip.suggested_title
                clip.reason = description or clip.reason
                # Mirror onto latest render if any
                render = (
                    session.query(Render)
                    .filter_by(clip_id=clip_id)
                    .order_by(Render.id.desc())
                    .first()
                )
                if render:
                    render.title = clip.suggested_title
                    render.description = clip.reason
        msg = "Métadonnées enregistrées"
    except Exception as exc:
        msg = f"Meta erreur: {exc}"
    return RedirectResponse(f"/dashboard/clips?flash={msg}", status_code=303)


@router.post("/renders/{render_id}/publish")
async def action_publish(render_id: int) -> RedirectResponse:
    try:
        with get_sync_session() as session:
            Orchestrator(session).run_publishing(render_id)
        msg = f"Publication render {render_id} OK"
    except Exception as exc:
        msg = f"Publish erreur: {exc}"
    return RedirectResponse(f"/dashboard/renders?flash={msg}", status_code=303)


@router.post("/agents/{agent}/pause")
async def action_pause(agent: AgentName) -> RedirectResponse:
    pause_agent(agent)
    return RedirectResponse(f"/dashboard?flash=Agent+{agent.value}+pausé", status_code=303)


@router.post("/agents/{agent}/resume")
async def action_resume(agent: AgentName) -> RedirectResponse:
    resume_agent(agent)
    return RedirectResponse(f"/dashboard?flash=Agent+{agent.value}+repris", status_code=303)
