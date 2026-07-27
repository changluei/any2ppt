from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import KnowledgeBase, SourceDocument


BUNDLE_VERSION = 1
KNOWLEDGE_BASE_IDS = [
    "official-chinese",
    "official-mathematics",
    "official-english",
    "personal",
]


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest() -> dict:
    with SessionLocal() as db:
        rows = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(KNOWLEDGE_BASE_IDS)).all()
        by_id = {item.id: item for item in rows}
        missing = [library_id for library_id in KNOWLEDGE_BASE_IDS if library_id not in by_id]
        if missing:
            raise RuntimeError(f"数据库尚未完成知识库迁移，缺少：{', '.join(missing)}")
        libraries = [by_id[library_id] for library_id in KNOWLEDGE_BASE_IDS]
        sources = (
            db.query(SourceDocument)
            .filter(SourceDocument.knowledge_base_id == "personal")
            .order_by(SourceDocument.created_at.asc())
            .all()
        )
        return {
            "bundle_version": BUNDLE_VERSION,
            "application": "any2ppt",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "knowledge_base_ids": KNOWLEDGE_BASE_IDS,
            "knowledge_bases": [
                {
                    "id": item.id,
                    "name": item.name,
                    "kind": item.kind,
                    "subject": item.subject,
                    "description": item.description,
                    "status": item.status,
                    "read_only": item.read_only,
                    "document_count": item.document_count,
                    "chunk_count": item.chunk_count,
                    "size_bytes": item.size_bytes,
                    "error_message": item.error_message,
                }
                for item in libraries
            ],
            "personal_sources": [
                {
                    "id": item.id,
                    "knowledge_base_id": "personal",
                    "original_name": item.original_name,
                    "stored_name": item.stored_name,
                    "media_type": item.media_type,
                    "size": item.size,
                    "sha256": item.sha256,
                    "status": item.status,
                    "error_message": item.error_message,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in sources
            ],
        }


def export_bundle(output: Path) -> Path:
    settings = get_settings()
    chroma_dir = settings.chroma_persist_dir.resolve()
    personal_dir = (settings.upload_dir / "personal").resolve()
    if not chroma_dir.is_dir() or not (chroma_dir / "chroma.sqlite3").is_file():
        raise SystemExit(f"Chroma 数据不存在：{chroma_dir}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"输出文件已经存在：{output}")

    source_bytes = directory_size(chroma_dir) + directory_size(personal_dir)
    free_bytes = shutil.disk_usage(output.parent).free
    if free_bytes < source_bytes:
        raise SystemExit(
            f"空间不足：源数据约 {source_bytes / 1024**3:.2f} GiB，"
            f"输出目录仅剩 {free_bytes / 1024**3:.2f} GiB"
        )

    manifest = build_manifest()
    with tempfile.TemporaryDirectory(prefix="any2ppt-kb-export-") as temp_name:
        manifest_path = Path(temp_name) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"开始打包：{manifest['knowledge_bases'][0]['chunk_count']:,} 语文片段，"
            f"{manifest['knowledge_bases'][1]['chunk_count']:,} 数学片段，"
            f"{manifest['knowledge_bases'][2]['chunk_count']:,} 英语片段，"
            f"{len(manifest['personal_sources'])} 份个人资料",
            flush=True,
        )
        with tarfile.open(output, mode="w:gz", compresslevel=6) as archive:
            archive.add(manifest_path, arcname="manifest.json")
            archive.add(chroma_dir, arcname="chroma")
            if personal_dir.is_dir():
                archive.add(personal_dir, arcname="uploads/personal")

    checksum = sha256_file(output)
    checksum_path = Path(f"{output}.sha256")
    checksum_path.write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    print(f"知识库迁移包：{output}", flush=True)
    print(f"校验文件：{checksum_path}", flush=True)
    print(f"压缩包大小：{output.stat().st_size / 1024**3:.2f} GiB", flush=True)
    return output


if __name__ == "__main__":
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(description="导出可交给其他 Any2PPT 实例的完整知识库迁移包")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path(f"/app/transfer/any2ppt-knowledge-{timestamp}.tar.gz"),
        help="输出 .tar.gz 路径，默认写入 /app/transfer",
    )
    args = parser.parse_args()
    export_bundle(args.output)
