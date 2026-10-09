"""Generate TikTok-style word-by-word ASS subtitles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shorts_pipeline.agents.editing.styles import StyleConfig, ass_color


def generate_ass(
    words: list[dict[str, Any]],
    *,
    style: StyleConfig,
    width: int = 1080,
    height: int = 1920,
    clip_start: float = 0.0,
    clip_end: float | None = None,
) -> str:
    """
    Build ASS content with current-word highlight.

    `words` items: {word, start, end} in absolute source timestamps.
    Output events are relative to the clip (start at 0).
    """
    primary = ass_color(style.primary_color)
    highlight = ass_color(style.highlight_color)
    outline = ass_color(style.outline_color)
    # Alignment 2 = bottom-center; margin V for bottom third
    margin_v = int(height * 0.28) if style.position == "bottom_third" else 80

    header = f"""[Script Info]
Title: Shorts Pipeline Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{primary},{highlight},{outline},&H80000000,-1,0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow},2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Filter words inside clip window
    end_limit = clip_end if clip_end is not None else float("inf")
    in_clip = [w for w in words if float(w["end"]) > clip_start and float(w["start"]) < end_limit]
    if not in_clip:
        return header

    lines: list[str] = [header]
    # Group into chunks of max_words_per_line for display windows
    chunk_size = max(1, style.max_words_per_line)
    for i in range(0, len(in_clip), chunk_size):
        chunk = in_clip[i : i + chunk_size]
        # For each word in chunk, emit an event spanning that word's duration
        # showing the whole chunk with the active word highlighted
        for j, active in enumerate(chunk):
            rel_start = max(0.0, float(active["start"]) - clip_start)
            rel_end = max(rel_start + 0.05, float(active["end"]) - clip_start)
            if clip_end is not None:
                rel_end = min(rel_end, clip_end - clip_start)
            text_parts: list[str] = []
            for k, w in enumerate(chunk):
                raw = str(w["word"]).strip()
                if not raw:
                    continue
                if k == j:
                    text_parts.append("{\\c" + highlight + "&\\b1}" + _ass_escape(raw) + "{\\r}")
                else:
                    text_parts.append(_ass_escape(raw))
            dialogue = " ".join(text_parts)
            lines.append(
                f"Dialogue: 0,{_ts(rel_start)},{_ts(rel_end)},Default,,0,0,0,,{dialogue}\n"
            )
    return "".join(lines)


def write_ass_file(content: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _ts(seconds: float) -> str:
    """ASS timestamp H:MM:SS.cs"""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = round((seconds - int(seconds)) * 100)
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
