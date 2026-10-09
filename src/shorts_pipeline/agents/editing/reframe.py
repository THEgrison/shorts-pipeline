"""9:16 reframing: face-centered crop with blur fallback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReframePlan:
    mode: str  # "face_crop" | "blur_center"
    # ffmpeg filter_complex fragment (video only, labeled [vout])
    filter_complex: str


def build_reframe_filter(
    *,
    width: int = 1080,
    height: int = 1920,
    face_center_x: float | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
) -> ReframePlan:
    """
    Build an ffmpeg filter for 9:16 output.

    If face_center_x (0-1 normalized) is known, crop a vertical window around it.
    Otherwise: blur full-frame background + centered fit (classic Shorts fallback).
    """
    if face_center_x is not None and source_width and source_height:
        # Target crop box 9:16 inside source
        crop_h = source_height
        crop_w = int(crop_h * width / height)
        if crop_w > source_width:
            crop_w = source_width
            crop_h = int(crop_w * height / width)
        cx = int(face_center_x * source_width)
        x = max(0, min(source_width - crop_w, cx - crop_w // 2))
        y = max(0, (source_height - crop_h) // 2)
        fc = f"[0:v]crop={crop_w}:{crop_h}:{x}:{y},scale={width}:{height}:flags=lanczos[vout]"
        return ReframePlan(mode="face_crop", filter_complex=fc)

    # Blurred background + centered foreground
    fc = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=20:5[bg];"
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vout]"
    )
    return ReframePlan(mode="blur_center", filter_complex=fc)


def detect_face_center_x(video_path: Path, *, sample_time_sec: float = 1.0) -> float | None:
    """
    Detect a face near sample_time and return normalized center x (0-1).
    Tries MediaPipe then OpenCV Haar; returns None on failure.
    """
    try:
        import cv2
    except ImportError:
        logger.warning("reframe.opencv_unavailable")
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_idx = int(sample_time_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None

    h, w = frame.shape[:2]

    # Try MediaPipe
    try:
        import mediapipe as mp

        with mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.5
        ) as detector:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = detector.process(rgb)
            if result.detections:
                box = result.detections[0].location_data.relative_bounding_box
                return float(box.xmin + box.width / 2)
    except Exception:
        logger.debug("reframe.mediapipe_failed")

    # OpenCV Haar fallback
    try:
        cascade_path = getattr(cv2, "data", None)
        haar = (
            cascade_path.haarcascades + "haarcascade_frontalface_default.xml"
            if cascade_path is not None
            else ""
        )
        if haar:
            cascade = cv2.CascadeClassifier(haar)  # type: ignore[attr-defined]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) > 0:
                x, _y, fw, _fh = max(faces, key=lambda f: f[2] * f[3])
                return float((x + fw / 2) / w)
    except Exception:
        logger.debug("reframe.haar_failed")

    del h  # unused except for potential future vertical tracking
    return None


def probe_dimensions(video_path: Path) -> tuple[int, int]:
    """Return (width, height) via ffprobe."""
    import json
    import subprocess

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        str(video_path),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    return 1280, 720
