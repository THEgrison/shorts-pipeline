"""Video download (yt-dlp) and audio extraction (ffmpeg)."""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class DownloadError(RuntimeError):
    """Raised when download or audio extraction fails."""


class VideoDownloader(ABC):
    """Abstract downloader for testability."""

    @abstractmethod
    def download(self, youtube_video_id: str, dest_dir: Path) -> Path:
        """Download video file; return path to media."""

    @abstractmethod
    def extract_audio(self, video_path: Path, dest_wav: Path) -> Path:
        """Extract mono 16kHz WAV for Whisper."""


class YtDlpDownloader(VideoDownloader):
    """Production downloader using yt-dlp + ffmpeg."""

    def download(self, youtube_video_id: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(dest_dir / f"{youtube_video_id}.%(ext)s")
        url = f"https://www.youtube.com/watch?v={youtube_video_id}"
        cmd = [
            "yt-dlp",
            "-f",
            "bv*[height<=720]+ba/b[height<=720]/best",
            "--merge-output-format",
            "mp4",
            "-o",
            out_tmpl,
            "--no-playlist",
            url,
        ]
        logger.info("download.start", video_id=youtube_video_id)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            msg = f"yt-dlp failed for {youtube_video_id}: {exc}"
            raise DownloadError(msg) from exc

        matches = list(dest_dir.glob(f"{youtube_video_id}.*"))
        media = [p for p in matches if p.suffix.lower() in {".mp4", ".mkv", ".webm"}]
        if not media:
            msg = f"No media file found after download for {youtube_video_id}"
            raise DownloadError(msg)
        path = media[0]
        logger.info("download.done", path=str(path), size=path.stat().st_size)
        return path

    def extract_audio(self, video_path: Path, dest_wav: Path) -> Path:
        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(dest_wav),
        ]
        if shutil.which("ffmpeg") is None:
            raise DownloadError("ffmpeg not found on PATH")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            msg = f"ffmpeg audio extract failed: {exc}"
            raise DownloadError(msg) from exc
        return dest_wav


class FakeDownloader(VideoDownloader):
    """Test double: copies a fixture file or writes a tiny placeholder."""

    def __init__(self, fixture_video: Path | None = None) -> None:
        self.fixture_video = fixture_video

    def download(self, youtube_video_id: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{youtube_video_id}.mp4"
        if self.fixture_video and self.fixture_video.exists():
            shutil.copy2(self.fixture_video, dest)
        else:
            # Minimal placeholder bytes (not a real mp4 — Whisper path mocked in tests)
            dest.write_bytes(b"\x00\x00fake-video")
        return dest

    def extract_audio(self, video_path: Path, dest_wav: Path) -> Path:
        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        # 44-byte WAV header-ish stub
        dest_wav.write_bytes(b"RIFF$" + b"\x00" * 36)
        return dest_wav
