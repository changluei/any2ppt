"""将离线 JSONL 数据集批量导入语文、数学、英语官方知识库。

脚本逐条规范字段、构造可追溯 chunk 和 embedding，并以批次写入 Chroma；
最终刷新 MySQL KnowledgeBase 统计。官方库只通过该运维入口更新。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.vector_store import ProjectVectorStore
from app.core.database import SessionLocal
from app.models import KnowledgeBase
from app.services.knowledge_base_service import ensure_knowledge_bases


SUBJECT_LIBRARY = {
    "语文": "official-chinese",
    "数学": "official-mathematics",
    "英语": "official-english",
}


def record_subject(record: dict) -> str:
    metadata = record.get("metadata") or {}
    return str(record.get("subject") or metadata.get("subject") or "")


def normalized_record(record: dict, library_id: str) -> dict:
    metadata = record.get("metadata") or {}
    chunk_id = str(record.get("chunk_id") or record.get("id") or "")
    source_id = str(record.get("source_id") or metadata.get("source_id") or metadata.get("doc_id") or chunk_id)
    content = str(record.get("content") or record.get("text") or "")
    if not chunk_id or not content:
        raise ValueError("记录缺少 chunk_id 或 content")
    return {
        "chunk_id": f"{library_id}:{chunk_id}",
        "source_id": source_id,
        "content": content,
        "filename": record.get("filename") or record.get("source_file") or metadata.get("filename") or metadata.get("source_file") or source_id,
        "location": record.get("location") or metadata.get("location") or metadata.get("section") or "",
        "content_hash": record.get("content_hash") or metadata.get("content_hash") or "",
        "heading": record.get("heading") or metadata.get("heading") or "",
    }


def import_file(source: Path, batch_size: int, reset: bool) -> None:
    if not source.is_file():
        raise SystemExit(f"找不到数据文件：{source}")
    db = SessionLocal()
    store = ProjectVectorStore()
    library_ids = list(SUBJECT_LIBRARY.values())
    buffers: dict[str, list[dict]] = defaultdict(list)
    source_ids: dict[str, set[str]] = defaultdict(set)
    byte_counts: dict[str, int] = defaultdict(int)
    accepted: dict[str, int] = defaultdict(int)
    skipped = 0

    try:
        ensure_knowledge_bases(db)
        for library_id in library_ids:
            library = db.get(KnowledgeBase, library_id)
            if reset:
                store.delete_project(library_id)
            library.status = "importing"
            library.error_message = None
            library.chunk_count = 0
            library.document_count = 0
        db.commit()

        with source.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    raw = json.loads(line)
                    library_id = SUBJECT_LIBRARY.get(record_subject(raw))
                    if not library_id:
                        skipped += 1
                        continue
                    row = normalized_record(raw, library_id)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise RuntimeError(f"第 {line_number} 行无效：{exc}") from exc
                buffers[library_id].append(row)
                source_ids[library_id].add(row["source_id"])
                byte_counts[library_id] += len(row["content"].encode("utf-8"))
                if len(buffers[library_id]) >= batch_size:
                    store.upsert_records(library_id, buffers[library_id])
                    accepted[library_id] += len(buffers[library_id])
                    buffers[library_id].clear()
                    if sum(accepted.values()) % (batch_size * 20) == 0:
                        print(
                            "已导入 " + " / ".join(
                                f"{key} {accepted[key]:,}" for key in library_ids
                            ),
                            flush=True,
                        )

        for library_id in library_ids:
            if buffers[library_id]:
                store.upsert_records(library_id, buffers[library_id])
                accepted[library_id] += len(buffers[library_id])
            library = db.get(KnowledgeBase, library_id)
            library.chunk_count = store.count(library_id)
            library.document_count = len(source_ids[library_id])
            library.size_bytes = byte_counts[library_id]
            library.status = "ready" if library.chunk_count else "empty"
            library.error_message = None
        db.commit()
        for library_id in library_ids:
            library = db.get(KnowledgeBase, library_id)
            print(
                f"{library.name}: {library.document_count:,} 份来源，"
                f"{library.chunk_count:,} 个片段",
                flush=True,
            )
        if skipped:
            print(f"跳过无法识别学科的记录：{skipped:,}", flush=True)
    except Exception as exc:
        db.rollback()
        for library_id in library_ids:
            library = db.get(KnowledgeBase, library_id)
            if library:
                library.status = "failed"
                library.error_message = str(exc)[:500]
        db.commit()
        raise
    finally:
        store.close()
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将语数英 JSONL 资料导入三个官方知识库")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/app/datasets/model_ready/primary_school_chunks.jsonl"),
    )
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--reset", action="store_true", help="导入前清空三个官方向量集合")
    args = parser.parse_args()
    import_file(args.source, max(16, args.batch_size), args.reset)
