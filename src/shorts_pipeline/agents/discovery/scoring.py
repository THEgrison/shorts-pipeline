"""Relevance scoring for discovered YouTube videos."""

from __future__ import annotations

from datetime import UTC, datetime

from shorts_pipeline.clients.youtube import YouTubeVideoSnippet
from shorts_pipeline.config import Settings


def compute_relevance_score(
    video: YouTubeVideoSnippet,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> float:
    """
    Score 0-100 from views, like ratio, velocity, freshness, duration, language.

    Weights are intentionally simple and documented in DECISIONS.md.
    """
    now = now or datetime.now(UTC)
    score = 0.0

    # Views (log-ish linear cap) — max 25
    views = max(video.view_count, 0)
    if views >= 1_000_000:
        score += 25
    elif views >= 100_000:
        score += 20
    elif views >= 10_000:
        score += 15
    elif views >= 1_000:
        score += 10
    elif views >= 100:
        score += 5

    # Like / view ratio — max 20
    if views > 0:
        ratio = video.like_count / views
        score += min(20.0, ratio * 400)  # 5% likes → 20 pts

    # Velocity (views / hour since publish) — max 20
    if video.published_at is not None:
        age_hours = max((now - video.published_at.astimezone(UTC)).total_seconds() / 3600, 0.1)
        velocity = views / age_hours
        if velocity >= 1000:
            score += 20
        elif velocity >= 100:
            score += 15
        elif velocity >= 10:
            score += 10
        elif velocity >= 1:
            score += 5

        # Freshness — max 15 (newer is better, within 30 days)
        age_days = age_hours / 24
        if age_days <= 1:
            score += 15
        elif age_days <= 7:
            score += 12
        elif age_days <= 30:
            score += 8
        elif age_days <= 90:
            score += 3

    # Duration ideal band — max 15
    dur = video.duration_sec or 0
    lo = settings.discovery_ideal_duration_min_sec
    hi = settings.discovery_ideal_duration_max_sec
    if lo <= dur <= hi:
        score += 15
    elif dur > 0 and (lo * 0.5 <= dur < lo or hi < dur <= hi * 1.25):
        score += 7

    # Language match — max 5
    lang = (video.language or "").lower()
    allowed = {a.lower() for a in settings.allowed_languages_list}
    if lang and any(lang.startswith(a) for a in allowed):
        score += 5
    elif not lang:
        score += 2  # unknown language: mild penalty avoidance

    return round(min(100.0, score), 2)
