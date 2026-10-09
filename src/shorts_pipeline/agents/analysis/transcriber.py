"""Word-level transcription via faster-whisper (mockable)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float
    probability: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "start": self.start,
            "end": self.end,
            "probability": self.probability,
        }


@dataclass
class TranscriptResult:
    language: str | None
    full_text: str
    words: list[WordTimestamp] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    duration_sec: float | None = None
    model: str | None = None


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio_path: Path) -> TranscriptResult:
        """Return word-level transcript."""


class FasterWhisperTranscriber(Transcriber):
    """Production transcriber using faster-whisper."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel

        device = self.settings.whisper_device
        if device == "auto":
            device = "cuda"
            try:
                self._model = WhisperModel(
                    self.settings.whisper_model, device=device, compute_type="float16"
                )
            except Exception:
                logger.warning("whisper.gpu_unavailable_falling_back_cpu")
                device = "cpu"
                self._model = WhisperModel(
                    self.settings.whisper_model, device=device, compute_type="int8"
                )
        else:
            compute = "float16" if device == "cuda" else "int8"
            self._model = WhisperModel(
                self.settings.whisper_model, device=device, compute_type=compute
            )
        logger.info("whisper.loaded", model=self.settings.whisper_model, device=device)
        return self._model

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        model = self._load()
        segments_iter, info = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            vad_filter=True,
        )
        words: list[WordTimestamp] = []
        segments: list[dict[str, Any]] = []
        texts: list[str] = []
        for seg in segments_iter:
            texts.append(seg.text.strip())
            segments.append(
                {"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip()}
            )
            if seg.words:
                for w in seg.words:
                    words.append(
                        WordTimestamp(
                            word=w.word.strip(),
                            start=float(w.start),
                            end=float(w.end),
                            probability=float(getattr(w, "probability", 1.0) or 1.0),
                        )
                    )
        return TranscriptResult(
            language=getattr(info, "language", None),
            full_text=" ".join(texts).strip(),
            words=words,
            segments=segments,
            duration_sec=float(getattr(info, "duration", 0) or 0) or None,
            model=self.settings.whisper_model,
        )


class FakeTranscriber(Transcriber):
    """Deterministic transcript for tests."""

    def __init__(self, result: TranscriptResult | None = None) -> None:
        self.result = result or TranscriptResult(
            language="fr",
            full_text=(
                "Bonjour tout le monde. Voici le secret que personne ne vous dit. "
                "La productivité vient de la régularité. Merci d'avoir regardé."
            ),
            words=[
                WordTimestamp("Bonjour", 0.0, 0.4),
                WordTimestamp("tout", 0.4, 0.6),
                WordTimestamp("le", 0.6, 0.7),
                WordTimestamp("monde.", 0.7, 1.0),
                WordTimestamp("Voici", 30.0, 30.3),
                WordTimestamp("le", 30.3, 30.4),
                WordTimestamp("secret", 30.4, 30.8),
                WordTimestamp("que", 30.8, 30.9),
                WordTimestamp("personne", 30.9, 31.3),
                WordTimestamp("ne", 31.3, 31.4),
                WordTimestamp("vous", 31.4, 31.6),
                WordTimestamp("dit.", 31.6, 32.0),
                WordTimestamp("La", 32.0, 32.2),
                WordTimestamp("productivité", 32.2, 32.8),
                WordTimestamp("vient", 32.8, 33.1),
                WordTimestamp("de", 33.1, 33.2),
                WordTimestamp("la", 33.2, 33.3),
                WordTimestamp("régularité.", 33.3, 34.0),
                WordTimestamp("Merci", 55.0, 55.3),
                WordTimestamp("d'avoir", 55.3, 55.6),
                WordTimestamp("regardé.", 55.6, 56.2),
            ],
            segments=[
                {"start": 0.0, "end": 1.0, "text": "Bonjour tout le monde."},
                {
                    "start": 30.0,
                    "end": 34.0,
                    "text": "Voici le secret que personne ne vous dit. La productivité vient de la régularité.",
                },
                {"start": 55.0, "end": 56.2, "text": "Merci d'avoir regardé."},
            ],
            duration_sec=60.0,
            model="fake",
        )

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        del audio_path
        return self.result
