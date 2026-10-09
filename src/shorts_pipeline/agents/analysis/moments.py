"""LLM-based highlight detection with structured JSON output."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, field_validator

from shorts_pipeline.agents.analysis.transcriber import TranscriptResult
from shorts_pipeline.clients.anthropic_client import AnthropicClient
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """Tu es un expert en montage de shorts viraux.
À partir d'une transcription horodatée, propose les meilleurs clips courts.
Contraintes strictes:
- durée entre {min_sec} et {max_sec} secondes
- commencer sur une phrase complète
- hook accrocheur dans les 3 premières secondes
- finir proprement (fin de phrase)
Réponds UNIQUEMENT avec un JSON:
{{"clips":[{{"start":0.0,"end":30.0,"score":0,"hook":"...","reason":"...","suggested_title":"...","suggested_hashtags":["#a"]}}]}}
"""


class MomentCandidate(BaseModel):
    start: float
    end: float
    score: float = Field(ge=0, le=100)
    hook: str
    reason: str
    suggested_title: str
    suggested_hashtags: list[str] = Field(default_factory=list)

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: float, info: Any) -> float:
        start = info.data.get("start", 0.0)
        if v <= start:
            msg = "end must be greater than start"
            raise ValueError(msg)
        return v

    @property
    def duration(self) -> float:
        return self.end - self.start


class MomentDetector(ABC):
    @abstractmethod
    def detect(self, transcript: TranscriptResult) -> list[MomentCandidate]:
        """Return ranked moment candidates."""


class ClaudeMomentDetector(MomentDetector):
    def __init__(self, client: AnthropicClient, settings: Settings | None = None) -> None:
        self.client = client
        self.settings = settings or get_settings()

    def detect(self, transcript: TranscriptResult) -> list[MomentCandidate]:
        system = SYSTEM_PROMPT.format(
            min_sec=self.settings.analysis_clip_min_sec,
            max_sec=self.settings.analysis_clip_max_sec,
        )
        # Compact transcript for the prompt
        lines: list[str] = []
        for seg in transcript.segments:
            lines.append(f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text']}")
        user = (
            f"Langue: {transcript.language or 'unknown'}\n"
            f"Durée: {transcript.duration_sec or '?'}s\n"
            f"Transcription:\n" + "\n".join(lines[:200])
        )
        data = self.client.create_json(system=system, user=user)
        clips_raw = data.get("clips") if isinstance(data, dict) else data
        candidates: list[MomentCandidate] = []
        for item in clips_raw or []:
            try:
                candidates.append(MomentCandidate.model_validate(item))
            except Exception:
                logger.warning("moments.invalid_candidate", item=item)
        return candidates


class FakeMomentDetector(MomentDetector):
    """Deterministic moments for tests."""

    def detect(self, transcript: TranscriptResult) -> list[MomentCandidate]:
        del transcript
        return [
            MomentCandidate(
                start=30.0,
                end=55.0,
                score=92,
                hook="Voici le secret que personne ne vous dit",
                reason="Hook fort + densité de parole élevée",
                suggested_title="Le secret de la productivité",
                suggested_hashtags=["#productivité", "#shorts", "#python"],
            ),
            MomentCandidate(
                start=0.0,
                end=25.0,
                score=60,
                hook="Bonjour tout le monde",
                reason="Intro correcte mais hook faible",
                suggested_title="Introduction",
                suggested_hashtags=["#intro"],
            ),
            MomentCandidate(
                start=40.0,
                end=70.0,  # overlaps with first — selection should drop
                score=80,
                hook="Encore un hook",
                reason="Chevauche le meilleur clip",
                suggested_title="Overlap",
                suggested_hashtags=["#x"],
            ),
        ]
