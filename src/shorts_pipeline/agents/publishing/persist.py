"""Persist publication records."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from shorts_pipeline.agents.publishing.agent import PublishingOutput
from shorts_pipeline.db.enums import PublicationStatus
from shorts_pipeline.db.models import Publication
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def persist_publication(
    session: Session,
    *,
    result: PublishingOutput,
    idempotency_key: str,
    scheduled_at: datetime | None = None,
) -> Publication:
    status = (
        PublicationStatus.DRY_RUN
        if result.dry_run
        else (PublicationStatus.PUBLISHED if result.success else PublicationStatus.FAILED)
    )
    pub = Publication(
        render_id=result.render_id,
        account_id=result.account_id,
        platform=result.platform,
        status=status,
        title=result.title,
        description=result.description,
        hashtags=" ".join(result.hashtags),
        scheduled_at=scheduled_at,
        published_at=datetime.now(UTC) if result.success else None,
        external_post_id=result.external_post_id,
        external_url=result.external_url,
        idempotency_key=idempotency_key,
        attempt_count=1,
        error_message=result.error,
    )
    session.add(pub)
    session.flush()
    logger.info(
        "publishing.persisted",
        publication_id=pub.id,
        status=status.value,
        platform=result.platform.value,
    )
    return pub
