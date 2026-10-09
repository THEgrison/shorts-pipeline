"""Connected social accounts with encrypted OAuth tokens."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from shorts_pipeline.db.base import Base, TimestampMixin
from shorts_pipeline.db.enums import Platform

if TYPE_CHECKING:
    from shorts_pipeline.db.models.publication import Publication


class Account(Base, TimestampMixin):
    """A publishing account (YouTube / TikTok / Instagram)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform", native_enum=False),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # e.g. {"slots": ["09:00", "14:00", "19:00"], "timezone": "Europe/Paris"}
    schedule_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    publications: Mapped[list[Publication]] = relationship(
        "Publication",
        back_populates="account",
    )
