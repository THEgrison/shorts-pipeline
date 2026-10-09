"""ffmpeg-based short renderer."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shorts_pipeline.agents.editing.reframe import (
    ReframePlan,
    build_reframe_filter,
    detect_face_center_x,
    probe_dimensions,
)
from shorts_pipeline.agents.editing.styles import StyleConfig
from shorts_pipeline.agents.editing.subtitles import generate_ass, write_ass_file
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class RenderError(RuntimeError):
    """ffmpeg render failure."""


@dataclass
class RenderRequest:
    source_video: Path
    output_video: Path
    start_sec: float
    end_sec: float
    words: list[dict[str, object]]
    style: StyleConfig
    subtitle_path: Path | None = None
    thumbnail_path: Path | None = None
    background_music: Path | None = None


@dataclass
class RenderResult:
    output_video: Path
    subtitle_path: Path
    thumbnail_path: Path
    duration_sec: float
    width: int
    height: int
    reframe_mode: str
    file_size_bytes: int


def render_short(request: RenderRequest, *, settings: Settings | None = None) -> RenderResult:
    """Cut, reframe 9:16, burn ASS captions, loudnorm, export H.264."""
    cfg = settings or get_settings()
    if shutil.which("ffmpeg") is None:
        raise RenderError("ffmpeg not found on PATH")

    duration = min(request.end_sec - request.start_sec, cfg.editing_max_duration_sec)
    if duration < 1:
        raise RenderError("clip duration too short")

    request.output_video.parent.mkdir(parents=True, exist_ok=True)
    sub_path = request.subtitle_path or request.output_video.with_suffix(".ass")
    thumb_path = request.thumbnail_path or request.output_video.with_suffix(".jpg")

    from typing import Any, cast

    words_for_ass = cast(list[dict[str, Any]], [dict(w) for w in request.words])
    ass_content = generate_ass(
        words_for_ass,
        style=request.style,
        width=cfg.editing_width,
        height=cfg.editing_height,
        clip_start=request.start_sec,
        clip_end=request.start_sec + duration,
    )
    write_ass_file(ass_content, sub_path)

    src_w, src_h = probe_dimensions(request.source_video)
    face_x = detect_face_center_x(
        request.source_video, sample_time_sec=request.start_sec + min(1.0, duration / 2)
    )
    plan: ReframePlan = build_reframe_filter(
        width=cfg.editing_width,
        height=cfg.editing_height,
        face_center_x=face_x,
        source_width=src_w,
        source_height=src_h,
    )

    # Escape ASS path for ffmpeg subtitles filter (Windows-hostile chars)
    ass_escaped = str(sub_path).replace("\\", "/").replace(":", "\\:")

    # Optional progress bar as colored overlay at bottom
    progress = ""
    if request.style.progress_bar:
        # simple growing bar via overlay eval — keep lightweight: drawbox full width thin
        bar_h = 8
        progress = f",drawbox=x=0:y=ih-{bar_h}:w=iw:h={bar_h}:color={request.style.progress_bar_color}:t=fill"

    filter_complex = f"{plan.filter_complex};[vout]ass='{ass_escaped}'{progress}[vfinal]"

    loudnorm = f"loudnorm=I={cfg.editing_loudnorm_lufs}:TP=-1.5:LRA=11"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{request.start_sec:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(request.source_video),
    ]

    audio_filter = loudnorm
    if request.background_music and request.background_music.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(request.background_music)])
        vol = request.style.background_music_volume
        filter_complex += (
            f";[0:a]{loudnorm}[a0];[1:a]volume={vol}[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[afinal]"
        )
        map_audio = ["-map", "[afinal]"]
    else:
        filter_complex += f";[0:a]{audio_filter}[afinal]"
        map_audio = ["-map", "[afinal]"]

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vfinal]",
            *map_audio,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(request.output_video),
        ]
    )

    logger.info(
        "render.start",
        output=str(request.output_video),
        duration=duration,
        reframe=plan.mode,
    )
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        # Fallback: simpler pipeline without face crop / ass if filter failed
        logger.warning("render.primary_failed", stderr=(exc.stderr or "")[-800:])
        _render_fallback(request, cfg, duration, sub_path)
    except subprocess.TimeoutExpired as exc:
        raise RenderError("ffmpeg timed out") from exc

    if not request.output_video.exists():
        raise RenderError("output video missing after ffmpeg")

    _extract_thumbnail(request.output_video, thumb_path)

    return RenderResult(
        output_video=request.output_video,
        subtitle_path=sub_path,
        thumbnail_path=thumb_path,
        duration_sec=duration,
        width=cfg.editing_width,
        height=cfg.editing_height,
        reframe_mode=plan.mode,
        file_size_bytes=request.output_video.stat().st_size,
    )


def _render_fallback(
    request: RenderRequest,
    cfg: Settings,
    duration: float,
    sub_path: Path,
) -> None:
    """Simpler scale+pad pipeline if complex filters fail."""
    ass_escaped = str(sub_path).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"scale={cfg.editing_width}:{cfg.editing_height}:force_original_aspect_ratio=decrease,"
        f"pad={cfg.editing_width}:{cfg.editing_height}:(ow-iw)/2:(oh-ih)/2,"
        f"ass='{ass_escaped}'"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{request.start_sec:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(request.source_video),
        "-vf",
        vf,
        "-af",
        f"loudnorm=I={cfg.editing_loudnorm_lufs}:TP=-1.5:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(request.output_video),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        msg = f"ffmpeg fallback failed: {(exc.stderr or '')[-500:]}"
        raise RenderError(msg) from exc


def _extract_thumbnail(video_path: Path, thumb_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-ss",
        "0.5",
        "-vframes",
        "1",
        str(thumb_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
    except subprocess.CalledProcessError:
        logger.warning("render.thumbnail_failed")
        thumb_path.write_bytes(b"")
