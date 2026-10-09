"""Application configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "shorts-pipeline"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    dry_run: bool = Field(default=True, description="Run pipeline without real publishing")
    log_level: str = "INFO"
    log_json: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8742
    secret_key: SecretStr = SecretStr("change-me-in-production-use-32-bytes")
    fernet_key: SecretStr = Field(
        default=SecretStr("change-me-generate-with-Fernet-generate-key"),
        description="Fernet key for encrypting OAuth tokens",
    )

    # --- Database ---
    database_url: str = "postgresql+asyncpg://shorts:shorts@localhost:5432/shorts_pipeline"
    database_url_sync: str = "postgresql+psycopg2://shorts:shorts@localhost:5432/shorts_pipeline"

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- Storage ---
    storage_backend: Literal["local"] = "local"
    storage_local_root: Path = Path("/data/shorts")
    storage_temp_dir: Path = Path("/data/shorts/tmp")

    # --- Human-in-the-loop ---
    require_review: bool = True

    # --- Discovery ---
    youtube_api_key: SecretStr | None = None
    youtube_quota_daily_limit: int = 10_000
    discovery_max_results_per_query: int = 25
    discovery_ideal_duration_min_sec: int = 480  # 8 min
    discovery_ideal_duration_max_sec: int = 3600  # 60 min
    discovery_allowed_languages: str = "fr,en"

    # --- Analysis ---
    whisper_model: str = "base"
    whisper_device: Literal["auto", "cuda", "cpu"] = "auto"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    analysis_max_clips_per_video: int = 5
    analysis_clip_min_sec: int = 20
    analysis_clip_max_sec: int = 60

    # --- Editing ---
    editing_width: int = 1080
    editing_height: int = 1920
    editing_max_duration_sec: int = 60
    editing_loudnorm_lufs: float = -14.0
    editing_default_style_template: str = "tiktok_default"

    # --- Publishing ---
    publishing_max_posts_per_day: int = 5
    publishing_jitter_seconds: int = 600
    youtube_oauth_client_id: SecretStr | None = None
    youtube_oauth_client_secret: SecretStr | None = None
    tiktok_client_key: SecretStr | None = None
    tiktok_client_secret: SecretStr | None = None
    meta_app_id: SecretStr | None = None
    meta_app_secret: SecretStr | None = None

    # --- Alerts ---
    alert_webhook_url: str | None = None
    alert_discord_webhook_url: str | None = None
    alert_telegram_bot_token: SecretStr | None = None
    alert_telegram_chat_id: str | None = None

    # --- Metrics ---
    metrics_enabled: bool = True
    metrics_port: int = 9090

    @property
    def allowed_languages_list(self) -> list[str]:
        return [
            lang.strip() for lang in self.discovery_allowed_languages.split(",") if lang.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache (useful in tests)."""
    get_settings.cache_clear()
