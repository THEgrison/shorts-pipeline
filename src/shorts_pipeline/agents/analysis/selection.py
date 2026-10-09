"""Select top-N non-overlapping clips with duration and hook constraints."""

from __future__ import annotations

from shorts_pipeline.agents.analysis.moments import MomentCandidate
from shorts_pipeline.agents.analysis.signals import AnalysisSignals
from shorts_pipeline.agents.analysis.transcriber import TranscriptResult
from shorts_pipeline.config import Settings


def _starts_on_sentence(transcript: TranscriptResult, start: float, *, tol: float = 0.35) -> bool:
    """True if `start` aligns with a segment / sentence start."""
    for seg in transcript.segments:
        if abs(float(seg["start"]) - start) <= tol:
            return True
    # Fallback: near a word that follows punctuation-ended previous word
    for i, word in enumerate(transcript.words):
        if abs(word.start - start) <= tol:
            if i == 0:
                return True
            prev = transcript.words[i - 1].word
            if prev.endswith((".", "!", "?", "…")):
                return True
    return False


def _boost_with_signals(candidate: MomentCandidate, signals: AnalysisSignals) -> float:
    score = candidate.score
    # +5 if an energy peak falls in the first 3 seconds of the clip
    if any(candidate.start <= p <= candidate.start + 3.0 for p in signals.energy_peaks):
        score += 5
    # +3 if a scene change is near the start
    if any(abs(p - candidate.start) <= 1.0 for p in signals.scene_changes):
        score += 3
    return min(100.0, score)


def overlaps(a: MomentCandidate, b: MomentCandidate) -> bool:
    return not (a.end <= b.start or b.end <= a.start)


def select_top_clips(
    candidates: list[MomentCandidate],
    *,
    transcript: TranscriptResult,
    signals: AnalysisSignals,
    settings: Settings,
    max_clips: int | None = None,
) -> list[MomentCandidate]:
    """
    Filter by duration / sentence start, boost with signals,
    greedily pick non-overlapping highest scores.
    """
    min_sec = settings.analysis_clip_min_sec
    max_sec = settings.analysis_clip_max_sec
    limit = max_clips if max_clips is not None else settings.analysis_max_clips_per_video

    scored: list[MomentCandidate] = []
    for c in candidates:
        if not (min_sec <= c.duration <= max_sec):
            continue
        if not _starts_on_sentence(transcript, c.start):
            # Soft: still keep but slight penalty via copy with lower score
            boosted = _boost_with_signals(c, signals) - 10
        else:
            boosted = _boost_with_signals(c, signals)
        scored.append(
            MomentCandidate(
                start=c.start,
                end=c.end,
                score=max(0.0, boosted),
                hook=c.hook,
                reason=c.reason,
                suggested_title=c.suggested_title,
                suggested_hashtags=c.suggested_hashtags,
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    selected: list[MomentCandidate] = []
    for c in scored:
        if any(overlaps(c, s) for s in selected):
            continue
        selected.append(c)
        if len(selected) >= limit:
            break
    return selected
