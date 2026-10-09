"""Load discovery niches from YAML config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class NicheConfig(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    min_duration_sec: int | None = None
    max_duration_sec: int | None = None


class DiscoveryConfig(BaseModel):
    niches: list[NicheConfig] = Field(default_factory=list)
    seed_channels: list[str] = Field(default_factory=list)


def load_discovery_config(path: Path | None = None) -> DiscoveryConfig:
    """Load niches YAML; returns empty config if file missing."""
    config_path = path or Path("config/niches.yaml")
    if not config_path.exists():
        return DiscoveryConfig()
    data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return DiscoveryConfig.model_validate(data)
