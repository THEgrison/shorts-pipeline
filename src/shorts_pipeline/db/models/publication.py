"""Publication records per platform."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shorts_pipeline.db.base import Base, TimestampMixin
from shorts_pipeline.db.enums import Platform, PublicationStatus

if TYPE_CHECKING:
    from shorts_pipeline.db.models.account import Account
    from shorts_pipeline.db.models.render import Render


class Publication(Base, TimestampMixin):
    """One publication attempt of a render on a platform account."""

    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint(
            "render_id",
            "account_id",
            "idempotency_key",
            name="uq_publications_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    render_id: Mapped[int] = mapped_column(
        ForeignKey("renders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform", native_enum=False, create_constraint=False),
        nullable=False,
        index=True,
    )
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status", native_enum=False),
        default=PublicationStatus.PENDING,
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    render: Mapped[Render] = relationship("Render", back_populates="publications")
    account: Mapped[Account] = relationship("Account", back_populates="publications")
