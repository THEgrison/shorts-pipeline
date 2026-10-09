"""Storage backends for media files."""

from shorts_pipeline.storage.base import StorageBackend
from shorts_pipeline.storage.local import LocalStorageBackend, get_storage

__all__ = ["LocalStorageBackend", "StorageBackend", "get_storage"]
