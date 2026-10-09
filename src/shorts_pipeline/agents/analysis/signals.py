"""Complementary signals: audio energy, scene changes, speech density."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shorts_pipeline.agents.analysis.transcriber import TranscriptResult
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class AnalysisSignals:
    energy_peaks: list[float] = field(default_factory=list)
    scene_changes: list[float] = field(default_factory=list)
    speech_density: list[dict[str, float]] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "energy_peaks": self.energy_peaks,
            "scene_changes": self.scene_changes,
            "speech_density": self.speech_density,
            **self.extras,
        }


def speech_density_from_transcript(
    transcript: TranscriptResult, *, window_sec: float = 10.0
) -> list[dict[str, float]]:
    """Words per second in sliding windows."""
    if not transcript.words:
        return []
    duration = transcript.duration_sec or (transcript.words[-1].end if transcript.words else 0)
    densities: list[dict[str, float]] = []
    t = 0.0
    while t < duration:
        end = t + window_sec
        count = sum(1 for w in transcript.words if t <= w.start < end)
        densities.append({"start": t, "end": end, "words_per_sec": count / window_sec})
        t = end
    return densities


def detect_energy_peaks(audio_path: Path, *, top_n: int = 10) -> list[float]:
    """Return timestamps (sec) of top RMS energy peaks. Falls back to empty on error."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        logger.warning("signals.librosa_unavailable")
        return []

    try:
        y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
        hop = 512
        rms = librosa.feature.rms(y=y, hop_length=hop)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
        if len(rms) == 0:
            return []
        # Local peaks: above mean + std
        threshold = float(rms.mean() + rms.std())
        candidates = [
            (float(times[i]), float(rms[i])) for i in range(len(rms)) if rms[i] >= threshold
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        # Non-max suppression: keep peaks at least 5s apart
        picked: list[float] = []
        for t, _ in candidates:
            if all(abs(t - p) >= 5.0 for p in picked):
                picked.append(t)
            if len(picked) >= top_n:
                break
        return sorted(picked)
    except Exception:
        logger.exception("signals.energy_failed")
        return []


def detect_scene_changes(video_path: Path) -> list[float]:
    """Detect scene cuts via PySceneDetect; empty list if unavailable."""
    try:
        from scenedetect import ContentDetector, detect
    except ImportError:
        logger.warning("signals.scenedetect_unavailable")
        return []

    try:
        scenes = detect(str(video_path), ContentDetector())
        return [float(start.get_seconds()) for start, _end in scenes]
    except Exception:
        logger.exception("signals.scenes_failed")
        return []


def collect_signals(
    *,
    video_path: Path | None,
    audio_path: Path | None,
    transcript: TranscriptResult,
) -> AnalysisSignals:
    """Gather complementary signals (best-effort)."""
    energy = detect_energy_peaks(audio_path) if audio_path and audio_path.exists() else []
    scenes = detect_scene_changes(video_path) if video_path and video_path.exists() else []
    density = speech_density_from_transcript(transcript)
    return AnalysisSignals(
        energy_peaks=energy,
        scene_changes=scenes,
        speech_density=density,
    )
