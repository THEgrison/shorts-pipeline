"""Analysis Agent tests with fake download / whisper / LLM."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from shorts_pipeline.agents.analysis.agent import AnalysisInput, build_test_analysis_agent
from shorts_pipeline.agents.analysis.moments import FakeMomentDetector, MomentCandidate
from shorts_pipeline.agents.analysis.selection import overlaps, select_top_clips
from shorts_pipeline.agents.analysis.signals import speech_density_from_transcript
from shorts_pipeline.agents.analysis.transcriber import FakeTranscriber
from shorts_pipeline.clients.anthropic_client import AnthropicClient
from shorts_pipeline.config import Settings
from shorts_pipeline.db.enums import LicenseBasis, VideoStatus
from shorts_pipeline.db.models import Clip, SourceVideo, Transcript
from shorts_pipeline.orchestrator.service import Orchestrator
from shorts_pipeline.storage.local import LocalStorageBackend


def test_select_top_clips_non_overlapping(settings: Settings) -> None:
    transcript = FakeTranscriber().transcribe(Path("."))
    detector = FakeMomentDetector()
    candidates = detector.detect(transcript)
    from shorts_pipeline.agents.analysis.signals import AnalysisSignals

    selected = select_top_clips(
        candidates,
        transcript=transcript,
        signals=AnalysisSignals(energy_peaks=[30.5], scene_changes=[30.0]),
        settings=settings,
        max_clips=5,
    )
    assert len(selected) >= 1
    assert selected[0].score >= selected[-1].score
    for i, a in enumerate(selected):
        for b in selected[i + 1 :]:
            assert not overlaps(a, b)


def test_speech_density() -> None:
    transcript = FakeTranscriber().transcribe(Path("."))
    density = speech_density_from_transcript(transcript, window_sec=10.0)
    assert density
    assert density[0]["words_per_sec"] >= 0


def test_analysis_agent_end_to_end(settings: Settings, tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "store")
    agent = build_test_analysis_agent(settings=settings, storage=storage)
    result = agent.run(
        AnalysisInput(
            source_video_id=1,
            youtube_video_id="abc123",
            work_dir=tmp_path / "work",
            dry_run=True,
        )
    )
    assert result.success
    assert result.storage_key
    assert result.transcript is not None
    assert result.transcript["words"]
    assert len(result.clips) >= 1
    assert result.clips[0].hook


def test_orchestrator_analysis_persists(
    sync_session: Session, settings: Settings, tmp_path: Path
) -> None:
    video = SourceVideo(
        youtube_video_id="analyze_me",
        youtube_channel_id="UCcc",
        title="Test",
        license="creativeCommon",
        license_basis=LicenseBasis.CREATIVE_COMMONS,
        status=VideoStatus.DISCOVERED,
        duration_sec=600,
    )
    sync_session.add(video)
    sync_session.commit()

    agent = build_test_analysis_agent(settings=settings, storage=LocalStorageBackend(tmp_path))
    orch = Orchestrator(sync_session, settings=settings, analysis_agent=agent)
    out = orch.run_analysis(video.id)
    assert out["success"]
    assert out["clip_ids"]

    sync_session.refresh(video)
    assert video.status == VideoStatus.ANALYZED
    assert sync_session.query(Transcript).filter_by(source_video_id=video.id).count() == 1
    assert sync_session.query(Clip).filter_by(source_video_id=video.id).count() >= 1

    # Idempotent
    out2 = orch.run_analysis(video.id)
    assert out2.get("idempotent") is True


def test_anthropic_client_json_parse(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": '```json\n{"clips":[{"start":1,"end":25,"score":80,'
                        '"hook":"h","reason":"r","suggested_title":"t",'
                        '"suggested_hashtags":["#a"]}]}\n```',
                    }
                ]
            },
        )

    client = AnthropicClient(
        api_key="test",
        settings=settings,
        transport=httpx.MockTransport(handler),
    )
    data = client.create_json(system="s", user="u")
    assert "clips" in data
    MomentCandidate.model_validate(data["clips"][0])
