"""面向生成流程的 RAG 检索封装。

它将向量库原始行转换成 Citation，检测相互矛盾的片段，并把“无足够证据”
作为显式状态返回，防止生成器把空检索误当成可靠资料。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.knowledge_base_service import search_knowledge_bases

from .schemas import Citation, LessonContext
from .vector_store import ProjectVectorStore


@dataclass(frozen=True)
class EvidenceSet:
    """检索片段、标准化引用、冲突提示和降级状态的集合。"""
    rows: list[dict]
    citations: list[Citation]
    sufficient: bool
    warnings: list[str]
    conflicts: list[str]


def _citations(rows: list[dict]) -> list[Citation]:
    """将向量库行去重并转换为可暴露的引用结构。"""
    return [
        Citation(
            source_id=row["source_id"],
            chunk_id=row["chunk_id"],
            filename=row["filename"],
            location=row["location"],
            quote=row["content"][:600],
            score=row.get("score"),
        )
        for row in rows
    ]


def _detect_conflicts(rows: list[dict]) -> list[str]:
    """对同一关键词附近的否定/数值差异做启发式冲突提示。"""
    """Detect only explicit numeric contradictions; uncertain cases stay warnings."""
    claims: dict[str, set[str]] = {}
    patterns = [
        ("课时", r"(\d+)\s*课时"),
        ("分钟", r"(\d+)\s*分钟"),
    ]
    for row in rows:
        for label, pattern in patterns:
            values = re.findall(pattern, row["content"])
            if values:
                claims.setdefault(label, set()).update(values)
    return [f"检索资料中的{label}表述不一致：{', '.join(sorted(values))}" for label, values in claims.items() if len(values) > 1]


def retrieve_evidence(
    context: LessonContext,
    query: str,
    *,
    store: ProjectVectorStore | None = None,
    top_k: int | None = None,
    min_score: float | None = None,
) -> EvidenceSet:
    """检索所选项目资料/知识库，并施加最低相关度阈值。"""
    settings = get_settings()
    vector_store = store or ProjectVectorStore()
    library_ids = list(context.selected_knowledge_base_ids)
    if context.selected_source_ids and "personal" not in library_ids:
        library_ids.append("personal")
    threshold = 0.0 if context.selected_source_ids else settings.ai_min_score if min_score is None else min_score
    rows = (
        search_knowledge_bases(
            library_ids,
            query,
            top_k=top_k or settings.ai_top_k,
            source_ids=context.selected_source_ids or None,
            store=vector_store,
            min_score=threshold,
        )
        if library_ids
        else []
    )
    # Compatibility path for documents indexed before the durable personal library
    # migration. New uploads are always indexed into ``personal``.
    if not rows:
        rows = vector_store.similarity_search(
            context.project_id,
            query,
            top_k=top_k or settings.ai_top_k,
            source_ids=context.selected_source_ids or None,
            min_score=threshold,
        )
    warnings: list[str] = []
    sufficient = bool(rows) and max(row["score"] for row in rows) >= max(settings.ai_min_score, 0.12)
    if not rows:
        warnings.append("没有检索到可用资料；通用教学建议不会伪装成教材或课标结论。")
    elif not sufficient:
        warnings.append("检索相关度较低，关键事实需要教师核对。")
    conflicts = _detect_conflicts(rows)
    warnings.extend(conflicts)
    return EvidenceSet(rows, _citations(rows), sufficient, warnings, conflicts)
