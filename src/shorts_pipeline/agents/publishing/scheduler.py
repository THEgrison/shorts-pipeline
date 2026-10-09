"""Publication scheduling: slots, daily caps, jitter, dedupe."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from shorts_pipeline.db.enums import PublicationStatus
from shorts_pipeline.db.models import Account, Publication
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def posts_today(session: Session, account_id: int, *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    return (
        session.query(func.count(Publication.id))
        .filter(
            Publication.account_id == account_id,
            Publication.created_at >= start,
            Publication.status.in_(
                [
                    PublicationStatus.SCHEDULED,
                    PublicationStatus.UPLOADING,
                    PublicationStatus.PUBLISHED,
                    PublicationStatus.DRY_RUN,
                ]
            ),
        )
        .scalar()
        or 0
    )


def can_publish_today(session: Session, account: Account, *, now: datetime | None = None) -> bool:
    return posts_today(session, account.id, now=now) < account.max_posts_per_day


def next_slot(
    account: Account,
    *,
    now: datetime | None = None,
    jitter_seconds: int = 600,
) -> datetime:
    """
    Pick the next schedule datetime from account.schedule_config slots.

    schedule_config example:
      {"slots": ["09:00", "14:00", "19:00"], "timezone": "UTC"}
    """
    now = now or datetime.now(UTC)
    cfg: dict[str, Any] = account.schedule_config or {}
    slots: list[str] = list(cfg.get("slots") or ["12:00"])
    # Interpret slots as UTC for simplicity (document in DECISIONS)
    candidates: list[datetime] = []
    for day_offset in range(0, 3):
        day = (now + timedelta(days=day_offset)).date()
        for slot in slots:
            hour, minute = (int(x) for x in slot.split(":")[:2])
            dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)
            if dt > now:
                candidates.append(dt)
    if not candidates:
        candidates = [now + timedelta(hours=1)]
    chosen = min(candidates)
    jitter = random.randint(0, max(0, jitter_seconds))
    return chosen + timedelta(seconds=jitter)


def already_published_identical(
    session: Session,
    *,
    render_id: int,
    account_id: int,
) -> Publication | None:
    """Prevent posting the same render twice to the same account."""
    return (
        session.query(Publication)
        .filter(
            Publication.render_id == render_id,
            Publication.account_id == account_id,
            Publication.status.in_(
                [
                    PublicationStatus.PUBLISHED,
                    PublicationStatus.DRY_RUN,
                    PublicationStatus.SCHEDULED,
                    PublicationStatus.UPLOADING,
                ]
            ),
        )
        .first()
    )
