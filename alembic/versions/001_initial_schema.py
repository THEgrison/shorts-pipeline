"""Initial schema: channels, videos, transcripts, clips, renders, accounts, publications, jobs, styles.

Revision ID: 001
Revises:
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "channels_whitelist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("youtube_channel_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("handle", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_owned", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels_whitelist")),
        sa.UniqueConstraint("youtube_channel_id", name=op.f("uq_channels_whitelist_youtube_channel_id")),
    )

    op.create_table(
        "style_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("config", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_style_templates")),
        sa.UniqueConstraint("name", name=op.f("uq_style_templates_name")),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("external_account_id", sa.String(length=128), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_posts_per_day", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("schedule_config", JSON_TYPE, nullable=True),
        sa.Column("metadata_json", JSON_TYPE, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
    )
    op.create_index(op.f("ix_accounts_platform"), "accounts", ["platform"], unique=False)
    op.create_index(
        op.f("ix_accounts_external_account_id"),
        "accounts",
        ["external_account_id"],
        unique=False,
    )

    op.create_table(
        "source_videos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("youtube_channel_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("comment_count", sa.BigInteger(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("license", sa.String(length=64), nullable=True),
        sa.Column("license_basis", sa.String(length=32), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="discovered"),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1024), nullable=True),
        sa.Column("raw_metadata", JSON_TYPE, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels_whitelist.id"],
            name=op.f("fk_source_videos_channel_id_channels_whitelist"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_videos")),
        sa.UniqueConstraint("youtube_video_id", name="uq_source_videos_youtube_video_id"),
    )
    op.create_index(op.f("ix_source_videos_youtube_video_id"), "source_videos", ["youtube_video_id"])
    op.create_index(op.f("ix_source_videos_youtube_channel_id"), "source_videos", ["youtube_channel_id"])
    op.create_index(op.f("ix_source_videos_status"), "source_videos", ["status"])

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_video_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("words", JSON_TYPE, nullable=False),
        sa.Column("segments", JSON_TYPE, nullable=True),
        sa.Column("whisper_model", sa.String(length=64), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_video_id"],
            ["source_videos.id"],
            name=op.f("fk_transcripts_source_video_id_source_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcripts")),
        sa.UniqueConstraint("source_video_id", name="uq_transcripts_source_video_id"),
    )

    op.create_table(
        "clips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_video_id", sa.Integer(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("hook", sa.String(length=500), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("suggested_title", sa.String(length=300), nullable=True),
        sa.Column("suggested_hashtags", JSON_TYPE, nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="analyzed"),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("signals", JSON_TYPE, nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_video_id"],
            ["source_videos.id"],
            name=op.f("fk_clips_source_video_id_source_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clips")),
    )
    op.create_index(op.f("ix_clips_source_video_id"), "clips", ["source_video_id"])
    op.create_index(op.f("ix_clips_status"), "clips", ["status"])

    op.create_table(
        "renders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("clip_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("thumbnail_key", sa.String(length=512), nullable=True),
        sa.Column("subtitle_key", sa.String(length=512), nullable=True),
        sa.Column("style_template_name", sa.String(length=128), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["clip_id"],
            ["clips.id"],
            name=op.f("fk_renders_clip_id_clips"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_renders")),
    )
    op.create_index(op.f("ix_renders_clip_id"), "renders", ["clip_id"])
    op.create_index(op.f("ix_renders_status"), "renders", ["status"])

    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("render_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_post_id", sa.String(length=128), nullable=True),
        sa.Column("external_url", sa.String(length=1024), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["render_id"],
            ["renders.id"],
            name=op.f("fk_publications_render_id_renders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_publications_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publications")),
        sa.UniqueConstraint(
            "render_id",
            "account_id",
            "idempotency_key",
            name="uq_publications_idempotency",
        ),
    )
    op.create_index(op.f("ix_publications_render_id"), "publications", ["render_id"])
    op.create_index(op.f("ix_publications_account_id"), "publications", ["account_id"])
    op.create_index(op.f("ix_publications_platform"), "publications", ["platform"])
    op.create_index(op.f("ix_publications_status"), "publications", ["status"])

    op.create_table(
        "jobs_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("source_video_id", sa.Integer(), nullable=True),
        sa.Column("clip_id", sa.Integer(), nullable=True),
        sa.Column("render_id", sa.Integer(), nullable=True),
        sa.Column("input_payload", JSON_TYPE, nullable=True),
        sa.Column("output_payload", JSON_TYPE, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_video_id"],
            ["source_videos.id"],
            name=op.f("fk_jobs_log_source_video_id_source_videos"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clip_id"],
            ["clips.id"],
            name=op.f("fk_jobs_log_clip_id_clips"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["render_id"],
            ["renders.id"],
            name=op.f("fk_jobs_log_render_id_renders"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs_log")),
    )
    op.create_index(op.f("ix_jobs_log_celery_task_id"), "jobs_log", ["celery_task_id"])
    op.create_index(op.f("ix_jobs_log_agent"), "jobs_log", ["agent"])
    op.create_index(op.f("ix_jobs_log_status"), "jobs_log", ["status"])
    op.create_index(op.f("ix_jobs_log_source_video_id"), "jobs_log", ["source_video_id"])
    op.create_index(op.f("ix_jobs_log_clip_id"), "jobs_log", ["clip_id"])


def downgrade() -> None:
    op.drop_table("jobs_log")
    op.drop_table("publications")
    op.drop_table("renders")
    op.drop_table("clips")
    op.drop_table("transcripts")
    op.drop_table("source_videos")
    op.drop_table("accounts")
    op.drop_table("style_templates")
    op.drop_table("channels_whitelist")
