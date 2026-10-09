"""Analysis Agent: download → transcribe → detect moments → select clips."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from shorts_pipeline.agents.analysis.downloader import (
    FakeDownloader,
    VideoDownloader,
    YtDlpDownloader,
)
from shorts_pipeline.agents.analysis.moments import (
    ClaudeMomentDetector,
    FakeMomentDetector,
    MomentCandidate,
    MomentDetector,
)
from shorts_pipeline.agents.analysis.selection import select_top_clips
from shorts_pipeline.agents.analysis.signals import AnalysisSignals, collect_signals
from shorts_pipeline.agents.analysis.transcriber import (
    FakeTranscriber,
    FasterWhisperTranscriber,
    Transcriber,
    TranscriptResult,
)
from shorts_pipeline.agents.base import Agent, AgentInput, AgentOutput
from shorts_pipeline.clients.anthropic_client import AnthropicClient
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.db.enums import AgentName
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.storage.base import StorageBackend

logger = get_logger(__name__)


class AnalysisInput(AgentInput):
    source_video_id: int
    youtube_video_id: str
    work_dir: Path | None = None


class SelectedClipOut(AgentOutput):
    start_sec: float
    end_sec: float
    score: float
    hook: str | None = None
    reason: str | None = None
    suggested_title: str | None = None
    suggested_hashtags: list[str] = Field(default_factory=list)
    rank: int = 1
    signals: dict[str, Any] | None = None


class AnalysisOutput(AgentOutput):
    source_video_id: int
    youtube_video_id: str
    storage_key: str | None = None
    audio_key: str | None = None
    transcript: dict[str, Any] | None = None
    clips: list[SelectedClipOut] = Field(default_factory=list)


class AnalysisAgent(Agent[AnalysisInput, AnalysisOutput]):
    """Full analysis pipeline with injectable collaborators for tests."""

    name = AgentName.ANALYSIS

    def __init__(
        self,
        *,
        downloader: VideoDownloader | None = None,
        transcriber: Transcriber | None = None,
        moment_detector: MomentDetector | None = None,
        storage: StorageBackend | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.downloader = downloader or self._default_downloader()
        self.transcriber = transcriber or self._default_transcriber()
        self.moment_detector = moment_detector or self._default_detector()
        self.storage = storage

    def _default_downloader(self) -> VideoDownloader:
        return YtDlpDownloader()

    def _default_transcriber(self) -> Transcriber:
        return FasterWhisperTranscriber(self.settings)

    def _default_detector(self) -> MomentDetector:
        key = self.settings.anthropic_api_key
        if key is not None and key.get_secret_value():
            client = AnthropicClient(api_key=key.get_secret_value(), settings=self.settings)
            return ClaudeMomentDetector(client, self.settings)
        logger.warning("analysis.using_fake_moment_detector_no_anthropic_key")
        return FakeMomentDetector()

    def run(self, input_data: AnalysisInput) -> AnalysisOutput:
        work = input_data.work_dir or (
            self.settings.storage_temp_dir / f"analysis_{input_data.youtube_video_id}"
        )
        work.mkdir(parents=True, exist_ok=True)

        video_path = self.downloader.download(input_data.youtube_video_id, work)
        audio_path = self.downloader.extract_audio(video_path, work / "audio.wav")

        storage_key: str | None = None
        audio_key: str | None = None
        if self.storage is not None:
            storage_key = self.storage.put_file(
                f"videos/{input_data.youtube_video_id}/{video_path.name}",
                video_path,
            )
            audio_key = self.storage.put_file(
                f"videos/{input_data.youtube_video_id}/audio.wav",
                audio_path,
            )

        transcript = self.transcriber.transcribe(audio_path)
        signals = collect_signals(
            video_path=video_path,
            audio_path=audio_path,
            transcript=transcript,
        )
        # Avoid expensive signal libs on tiny fake files
        if isinstance(self.downloader, FakeDownloader):
            signals = AnalysisSignals(
                energy_peaks=[30.5, 32.0],
                scene_changes=[30.0],
                speech_density=signals.speech_density
                or [{"start": 30.0, "end": 40.0, "words_per_sec": 2.5}],
            )

        raw_moments = self.moment_detector.detect(transcript)
        selected = select_top_clips(
            raw_moments,
            transcript=transcript,
            signals=signals,
            settings=self.settings,
        )

        clips_out = [
            SelectedClipOut(
                success=True,
                start_sec=c.start,
                end_sec=c.end,
                score=c.score,
                hook=c.hook,
                reason=c.reason,
                suggested_title=c.suggested_title,
                suggested_hashtags=c.suggested_hashtags,
                rank=i + 1,
                signals=signals.to_dict(),
            )
            for i, c in enumerate(selected)
        ]

        logger.info(
            "analysis.completed",
            youtube_video_id=input_data.youtube_video_id,
            clips=len(clips_out),
            words=len(transcript.words),
        )
        return AnalysisOutput(
            success=True,
            message=f"Analyzed {input_data.youtube_video_id}: {len(clips_out)} clips",
            source_video_id=input_data.source_video_id,
            youtube_video_id=input_data.youtube_video_id,
            storage_key=storage_key,
            audio_key=audio_key,
            transcript=_transcript_to_dict(transcript),
            clips=clips_out,
        )


def _transcript_to_dict(t: TranscriptResult) -> dict[str, Any]:
    return {
        "language": t.language,
        "full_text": t.full_text,
        "words": [w.to_dict() for w in t.words],
        "segments": t.segments,
        "duration_sec": t.duration_sec,
        "whisper_model": t.model,
    }


def build_test_analysis_agent(
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
) -> AnalysisAgent:
    """Factory used by tests and DRY_RUN without external services."""
    return AnalysisAgent(
        downloader=FakeDownloader(),
        transcriber=FakeTranscriber(),
        moment_detector=FakeMomentDetector(),
        storage=storage,
        settings=settings or get_settings(),
    )


# Re-export for typing convenience
__all__ = [
    "AnalysisAgent",
    "AnalysisInput",
    "AnalysisOutput",
    "MomentCandidate",
    "SelectedClipOut",
    "build_test_analysis_agent",
]
