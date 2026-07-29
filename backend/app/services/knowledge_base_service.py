"""四个持久知识库的目录初始化、选择校验与跨库检索。

这里维护官方语数英和 personal 的固定定义；实际 chunk 与向量检索由
ProjectVectorStore 完成。
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.ai.vector_store import ProjectVectorStore
from app.models import KnowledgeBase, SourceDocument


KNOWLEDGE_BASE_DEFINITIONS = (
    {
        "id": "official-chinese",
        "name": "官方语文知识库",
        "kind": "official",
        "subject": "语文",
        "description": "课标、教材知识、阅读与写作教学资料",
        "read_only": True,
    },
    {
        "id": "official-mathematics",
        "name": "官方数学知识库",
        "kind": "official",
        "subject": "数学",
        "description": "小学数学概念、题型、方法与课程资料",
        "read_only": True,
    },
    {
        "id": "official-english",
        "name": "官方英语知识库",
        "kind": "official",
        "subject": "英语",
        "description": "小学英语词汇、语法、阅读与课堂活动资料",
        "read_only": True,
    },
    {
        "id": "personal",
        "name": "个人知识库",
        "kind": "personal",
        "subject": "",
        "description": "使用过程中上传并持续积累的个人资料",
        "read_only": False,
    },
)
KNOWLEDGE_BASE_IDS = {row["id"] for row in KNOWLEDGE_BASE_DEFINITIONS}


def ensure_knowledge_bases(db: Session) -> list[KnowledgeBase]:
    """幂等创建或修正四个内置知识库，保留已有统计和资料。"""
    existing = {row.id: row for row in db.query(KnowledgeBase).all()}
    changed = False
    for definition in KNOWLEDGE_BASE_DEFINITIONS:
        item = existing.get(definition["id"])
        if not item:
            item = KnowledgeBase(**definition, status="empty")
            db.add(item)
            existing[item.id] = item
            changed = True
        else:
            for key in ("name", "kind", "subject", "description", "read_only"):
                if getattr(item, key) != definition[key]:
                    setattr(item, key, definition[key])
                    changed = True
    if changed:
        db.commit()
    personal = existing["personal"]
    personal.document_count = db.query(SourceDocument).filter_by(
        knowledge_base_id="personal",
        status="ready",
    ).count()
    personal.size_bytes = sum(
        row[0] or 0
        for row in db.query(SourceDocument.size).filter_by(
            knowledge_base_id="personal",
            status="ready",
        ).all()
    )
    try:
        personal.chunk_count = ProjectVectorStore().count("personal")
        personal.status = "ready" if personal.chunk_count else "empty"
        personal.error_message = None
    except Exception as exc:
        personal.status = "failed"
        personal.error_message = str(exc)[:500]
    db.commit()
    order = {definition["id"]: index for index, definition in enumerate(KNOWLEDGE_BASE_DEFINITIONS)}
    return sorted(existing.values(), key=lambda row: order.get(row.id, len(order)))


def validate_knowledge_base_ids(db: Session, ids: Iterable[str], *, require_ready: bool = True) -> list[str]:
    """去重并验证 ID；生成时可要求库已 ready，personal 空库除外。"""
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    rows = {
        row.id: row
        for row in db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(unique)).all()
    }
    missing = [library_id for library_id in unique if library_id not in rows]
    if missing:
        raise ValueError(f"知识库不存在：{', '.join(missing)}")
    if require_ready:
        unavailable = [
            library_id
            for library_id in unique
            if rows[library_id].status not in {"ready", "empty"}
        ]
        if unavailable:
            raise RuntimeError(f"知识库尚未就绪：{', '.join(unavailable)}")
    return unique


def search_knowledge_bases(
    library_ids: list[str],
    query: str,
    top_k: int,
    source_ids: list[str] | None = None,
    *,
    store: ProjectVectorStore | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """逐库检索、按 source/chunk 去重，再返回全局得分最高的 top_k。"""
    vector_store = store or ProjectVectorStore()
    merged: dict[tuple[str, str], dict] = {}
    for library_id in library_ids:
        filters = source_ids if library_id == "personal" and source_ids else None
        for row in vector_store.similarity_search(
            library_id,
            query,
            top_k=top_k,
            source_ids=filters,
            min_score=min_score,
        ):
            enriched = {**row, "knowledge_base_id": library_id}
            key = (str(row.get("source_id", "")), str(row.get("chunk_id", "")))
            if key not in merged or enriched["score"] > merged[key]["score"]:
                merged[key] = enriched
    return sorted(
        merged.values(),
        key=lambda row: (-float(row.get("score", 0)), str(row.get("chunk_id", ""))),
    )[:top_k]
