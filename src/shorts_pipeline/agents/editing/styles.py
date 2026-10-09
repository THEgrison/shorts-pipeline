"""Load subtitle / editing style templates from YAML or DB-shaped dicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class StyleConfig(BaseModel):
    font_name: str = "Montserrat"
    font_size: int = 72
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFE566"
    outline_color: str = "#000000"
    outline_width: int = 4
    shadow: int = 2
    position: str = "bottom_third"
    max_words_per_line: int = 3
    animation: str = "pop"
    progress_bar: bool = True
    progress_bar_color: str = "#FFE566"
    intro_path: str | None = None
    outro_path: str | None = None
    background_music_volume: float = 0.08


class StyleTemplateData(BaseModel):
    name: str
    description: str | None = None
    is_default: bool = False
    config: StyleConfig = Field(default_factory=StyleConfig)


def load_style_template(name: str, *, styles_dir: Path | None = None) -> StyleTemplateData:
    """Load `config/styles/{name}.yaml`."""
    root = styles_dir or Path("config/styles")
    path = root / f"{name}.yaml"
    if not path.exists():
        return StyleTemplateData(name=name, is_default=True, config=StyleConfig())
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return StyleTemplateData.model_validate(data)


def ass_color(hex_color: str, *, alpha: str = "00") -> str:
    """Convert #RRGGBB to ASS &HAABBGGRR."""
    c = hex_color.lstrip("#")
    if len(c) != 6:
        c = "FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()
