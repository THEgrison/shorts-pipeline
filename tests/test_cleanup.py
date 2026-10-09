"""Temp cleanup tests."""

from __future__ import annotations

import os
import time
from pathlib import Path

from shorts_pipeline.config import Settings
from shorts_pipeline.orchestrator.cleanup import cleanup_temp_files


def test_cleanup_removes_old_files(settings: Settings, tmp_path: Path) -> None:
    old = tmp_path / "old.bin"
    old.write_bytes(b"12345")
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))
    fresh = tmp_path / "fresh.bin"
    fresh.write_bytes(b"abc")

    cfg = settings.model_copy(update={"storage_temp_dir": tmp_path})
    result = cleanup_temp_files(settings=cfg, max_age_hours=24)
    assert result["files"] >= 1
    assert not old.exists()
    assert fresh.exists()
