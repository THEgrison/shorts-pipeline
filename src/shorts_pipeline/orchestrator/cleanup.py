"""Temporary media cleanup."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def cleanup_temp_files(
    *,
    settings: Settings | None = None,
    max_age_hours: float = 24.0,
) -> dict[str, int]:
    """
    Delete files under storage_temp_dir older than max_age_hours.

    Returns counts of removed files/dirs and bytes freed.
    """
    cfg = settings or get_settings()
    root = Path(cfg.storage_temp_dir)
    if not root.exists():
        return {"files": 0, "dirs": 0, "bytes": 0}

    cutoff = time.time() - max_age_hours * 3600
    files = 0
    dirs = 0
    freed = 0
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                freed += path.stat().st_size
                path.unlink(missing_ok=True)
                files += 1
            elif path.is_dir() and path != root and not any(path.iterdir()):
                path.rmdir()
                dirs += 1
        except OSError:
            logger.warning("cleanup.skip", path=str(path))
    logger.info("cleanup.done", files=files, dirs=dirs, bytes=freed)
    return {"files": files, "dirs": dirs, "bytes": freed}


def cleanup_orphaned_workdir(work_dir: Path) -> None:
    """Remove a single analysis/edit work directory."""
    if work_dir.exists() and work_dir.is_dir():
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.info("cleanup.workdir", path=str(work_dir))
