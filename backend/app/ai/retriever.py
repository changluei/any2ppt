from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings

from .schemas import Citation, LessonContext
from .vector_store import ProjectVectorStore


@dataclass(frozen=True)
class EvidenceSet:
    rows: list[dict]
    citations: list[Citation]
    sufficient: bool
    warnings: list[str]
    conflicts: list[str]


def _citations(rows: list[dict]) -> list[Citation]:
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
    settings = get_settings()
    vector_store = store or ProjectVectorStore()
    rows = vector_store.similarity_search(
        context.project_id,
        query,
        top_k=top_k or settings.ai_top_k,
        source_ids=context.selected_source_ids or None,
        min_score=settings.ai_min_score if min_score is None else min_score,
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
