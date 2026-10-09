"""Local filesystem storage backend."""

from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.storage.base import StorageBackend

logger = get_logger(__name__)


class LocalStorageBackend(StorageBackend):
    """Store files under a mounted local root directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        path = (self.root / safe).resolve()
        if not str(path).startswith(str(self.root)):
            msg = f"Storage key escapes root: {key}"
            raise ValueError(msg)
        return path

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def put_file(self, key: str, source: Path) -> str:
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        logger.debug("storage.put_file", key=key, source=str(source))
        return key

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        del content_type  # unused for local backend
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.debug("storage.put_bytes", key=key, size=len(data))
        return key

    def open_read(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def download_to(self, key: str, destination: Path) -> Path:
        source = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()
            logger.debug("storage.delete", key=key)
        elif path.is_dir():
            shutil.rmtree(path)
            logger.debug("storage.delete_dir", key=key)

    def url_or_path(self, key: str) -> str:
        return str(self._resolve(key))

    def list_keys(self, prefix: str) -> list[str]:
        base = self._resolve(prefix) if prefix else self.root
        if not base.exists():
            return []
        if base.is_file():
            return [prefix]
        keys: list[str] = []
        for path in base.rglob("*"):
            if path.is_file():
                keys.append(str(path.relative_to(self.root)))
        return sorted(keys)


@lru_cache
def get_storage(settings: Settings | None = None) -> StorageBackend:
    """Return the configured storage backend singleton."""
    cfg = settings or get_settings()
    if cfg.storage_backend == "local":
        return LocalStorageBackend(cfg.storage_local_root)
    msg = f"Unsupported storage backend: {cfg.storage_backend}"
    raise ValueError(msg)
