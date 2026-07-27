from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import import_knowledge_bundle


def write_archive(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_safe_extract_rejects_parent_traversal(tmp_path):
    archive_path = tmp_path / "unsafe.tar.gz"
    write_archive(archive_path, {"../outside.txt": b"unsafe"})
    with tarfile.open(archive_path, "r:*") as archive:
        with pytest.raises(SystemExit, match="不安全路径"):
            import_knowledge_bundle.safe_extract(archive, tmp_path / "extract")


def test_invalid_bundle_keeps_existing_data(tmp_path, monkeypatch):
    chroma = tmp_path / "data" / "chroma"
    personal = tmp_path / "data" / "uploads" / "personal"
    chroma.mkdir(parents=True)
    personal.mkdir(parents=True)
    (chroma / "sentinel.txt").write_text("keep", encoding="utf-8")
    (personal / "sentinel.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        import_knowledge_bundle,
        "get_settings",
        lambda: SimpleNamespace(chroma_persist_dir=chroma, upload_dir=personal.parent),
    )
    archive_path = tmp_path / "invalid.tar.gz"
    manifest = {
        "bundle_version": 1,
        "knowledge_base_ids": sorted(import_knowledge_bundle.EXPECTED_IDS),
    }
    write_archive(
        archive_path,
        {"manifest.json": json.dumps(manifest).encode("utf-8")},
    )

    with pytest.raises(RuntimeError, match="缺少"):
        import_knowledge_bundle.import_bundle(archive_path, replace=True)

    assert (chroma / "sentinel.txt").read_text("utf-8") == "keep"
    assert (personal / "sentinel.txt").read_text("utf-8") == "keep"
