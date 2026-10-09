"""Pipeline control endpoints (orchestrator + review)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shorts_pipeline.db.enums import AgentName
from shorts_pipeline.db.session import get_sync_session
from shorts_pipeline.orchestrator.pause import is_agent_paused, pause_agent, resume_agent
from shorts_pipeline.orchestrator.service import Orchestrator
from shorts_pipeline.workers.tasks import (
    advance_pipeline,
    run_discovery,
    run_full_dummy_pipeline,
)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


class DiscoveryRequest(BaseModel):
    niches: list[str] = Field(default_factory=list)
    async_mode: bool = True


class ClipReviewRequest(BaseModel):
    notes: str | None = None


class AgentPauseRequest(BaseModel):
    agent: AgentName


@router.post("/discovery")
def trigger_discovery(body: DiscoveryRequest) -> dict[str, object]:
    """Enqueue or run discovery."""
    if body.async_mode:
        async_result = run_discovery.delay(body.niches)
        return {"queued": True, "task_id": async_result.id}
    with get_sync_session() as session:
        return Orchestrator(session).run_discovery(niches=body.niches)


@router.post("/advance")
def trigger_advance(async_mode: bool = True) -> dict[str, object]:
    """Advance pending pipeline items."""
    if async_mode:
        async_result = advance_pipeline.delay()
        return {"queued": True, "task_id": async_result.id}
    with get_sync_session() as session:
        return {"success": True, "summary": Orchestrator(session).advance_pending()}


@router.post("/dummy-e2e")
def trigger_dummy_e2e(async_mode: bool = False) -> dict[str, object]:
    """Run the full dummy pipeline (sync by default for smoke tests)."""
    if async_mode:
        async_result = run_full_dummy_pipeline.delay()
        return {"queued": True, "task_id": async_result.id}
    result: dict[str, object] = run_full_dummy_pipeline()
    return result


@router.post("/clips/{clip_id}/approve")
def approve_clip(clip_id: int) -> dict[str, object]:
    with get_sync_session() as session:
        orch = Orchestrator(session)
        try:
            clip = orch.approve_clip(clip_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"id": clip.id, "status": clip.status.value}


@router.post("/clips/{clip_id}/reject")
def reject_clip(clip_id: int, body: ClipReviewRequest | None = None) -> dict[str, object]:
    with get_sync_session() as session:
        orch = Orchestrator(session)
        try:
            clip = orch.reject_clip(clip_id, notes=body.notes if body else None)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"id": clip.id, "status": clip.status.value}


@router.post("/agents/pause")
def pause(body: AgentPauseRequest) -> dict[str, object]:
    pause_agent(body.agent)
    return {"agent": body.agent.value, "paused": True}


@router.post("/agents/resume")
def resume(body: AgentPauseRequest) -> dict[str, object]:
    resume_agent(body.agent)
    return {"agent": body.agent.value, "paused": False}


@router.get("/agents/{agent}/status")
def agent_status(agent: AgentName) -> dict[str, object]:
    return {"agent": agent.value, "paused": is_agent_paused(agent)}
