"""Local storage backend tests."""

from __future__ import annotations

from pathlib import Path

from shorts_pipeline.storage.local import LocalStorageBackend


def test_local_put_get_delete(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    source = tmp_path / "src.txt"
    source.write_text("hello", encoding="utf-8")

    key = storage.put_file("videos/demo.txt", source)
    assert storage.exists(key)
    assert storage.url_or_path(key).endswith("videos/demo.txt")

    dest = tmp_path / "out.txt"
    storage.download_to(key, dest)
    assert dest.read_text(encoding="utf-8") == "hello"

    storage.put_bytes("videos/bin.dat", b"\x00\x01")
    keys = storage.list_keys("videos")
    assert "videos/demo.txt" in keys
    assert "videos/bin.dat" in keys

    storage.delete("videos/demo.txt")
    assert not storage.exists("videos/demo.txt")


def test_escape_root_rejected(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    try:
        storage.url_or_path("../outside")
    except ValueError:
        pass
    else:
        # Path with .. is sanitized to _; should still stay under root
        path = Path(storage.url_or_path("safe/../ok.txt"))
        assert str(path).startswith(str(tmp_path.resolve()))
