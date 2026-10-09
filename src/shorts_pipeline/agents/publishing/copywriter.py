"""Generate platform-specific title/description/hashtags."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from shorts_pipeline.clients.anthropic_client import AnthropicClient
from shorts_pipeline.db.enums import Platform
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class CopyPack(BaseModel):
    title: str
    description: str
    hashtags: list[str] = Field(default_factory=list)


class Copywriter(ABC):
    @abstractmethod
    def generate(
        self,
        *,
        platform: Platform,
        seed_title: str | None,
        seed_description: str | None,
        seed_hashtags: list[str] | None,
        language: str = "fr",
    ) -> CopyPack:
        """Return platform-adapted copy."""


class TemplateCopywriter(Copywriter):
    """Deterministic copywriter (no LLM) — default for dry-run/tests."""

    def generate(
        self,
        *,
        platform: Platform,
        seed_title: str | None,
        seed_description: str | None,
        seed_hashtags: list[str] | None,
        language: str = "fr",
    ) -> CopyPack:
        title = (seed_title or "Nouveau short").strip()
        if platform == Platform.YOUTUBE_SHORTS and len(title) > 100:
            title = title[:97] + "..."
        if platform == Platform.TIKTOK and len(title) > 150:
            title = title[:147] + "..."
        desc = (seed_description or "").strip()
        tags = list(seed_hashtags or ["#shorts", "#viral"])
        if platform == Platform.YOUTUBE_SHORTS and "#Shorts" not in tags:
            tags.append("#Shorts")
        if platform == Platform.INSTAGRAM_REELS and "#reels" not in [t.lower() for t in tags]:
            tags.append("#reels")
        del language
        return CopyPack(title=title, description=desc, hashtags=tags)


class ClaudeCopywriter(Copywriter):
    def __init__(self, client: AnthropicClient) -> None:
        self.client = client
        self.fallback = TemplateCopywriter()

    def generate(
        self,
        *,
        platform: Platform,
        seed_title: str | None,
        seed_description: str | None,
        seed_hashtags: list[str] | None,
        language: str = "fr",
    ) -> CopyPack:
        try:
            data = self.client.create_json(
                system=(
                    "Tu rédiges des titres/descriptions pour shorts. "
                    "Réponds uniquement en JSON "
                    '{"title":"...","description":"...","hashtags":["#a"]}'
                ),
                user=(
                    f"Plateforme: {platform.value}\nLangue: {language}\n"
                    f"Titre: {seed_title}\nDescription: {seed_description}\n"
                    f"Hashtags: {seed_hashtags}"
                ),
            )
            return CopyPack.model_validate(data)
        except Exception:
            logger.exception("copywriter.llm_failed_using_template")
            return self.fallback.generate(
                platform=platform,
                seed_title=seed_title,
                seed_description=seed_description,
                seed_hashtags=seed_hashtags,
                language=language,
            )
