"""Abstract storage interface (local now, S3/MinIO later)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StorageBackend(ABC):
    """File storage abstraction for pipeline media assets."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if object exists."""

    @abstractmethod
    def put_file(self, key: str, source: Path) -> str:
        """Copy a local file into storage. Returns the storage key."""

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """Write raw bytes. Returns the storage key."""

    @abstractmethod
    def open_read(self, key: str) -> BinaryIO:
        """Open object for reading."""

    @abstractmethod
    def download_to(self, key: str, destination: Path) -> Path:
        """Download object to a local path. Returns destination."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete object if it exists (no-op if missing)."""

    @abstractmethod
    def url_or_path(self, key: str) -> str:
        """Return a filesystem path or URL usable by ffmpeg / dashboard."""

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]:
        """List keys under a prefix."""

    def ensure_dir_key(self, key: str) -> str:
        """Normalize a directory-like key (trailing slash stripped for local use)."""
        return key.strip("/")
