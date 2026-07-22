from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .graph import review_artifacts
from .skills import route_intent
from .vector_store import ProjectVectorStore


@dataclass(frozen=True)
class GoldenQuery:
    project_id: str
    query: str
    expected_source_id: str | None
    source_ids: list[str] | None = None


def evaluate_retrieval(
    store: ProjectVectorStore,
    queries: Iterable[GoldenQuery],
    *,
    top_k: int = 3,
    min_score: float = 0.0,
) -> dict[str, Any]:
    cases = list(queries)
    hits = 0
    empty = 0
    details = []
    for case in cases:
        rows = store.similarity_search(
            case.project_id,
            case.query,
            top_k=top_k,
            source_ids=case.source_ids,
            min_score=min_score,
        )
        if not rows:
            empty += 1
        actual = [row["source_id"] for row in rows]
        matched = (not rows) if case.expected_source_id is None else case.expected_source_id in actual
        hits += int(matched)
        details.append({"query": case.query, "expected": case.expected_source_id, "actual": actual, "hit": matched})
    total = len(cases)
    return {
        "total": total,
        "top3_hits": hits,
        "top3_hit_rate": round(hits / total, 4) if total else 0.0,
        "empty_retrievals": empty,
        "details": details,
    }


def evaluate_router(cases: Iterable[tuple[str, str | None]]) -> dict[str, Any]:
    rows = []
    correct = 0
    for text, expected in cases:
        actual = route_intent(text)
        matched = actual == expected
        correct += int(matched)
        rows.append({"text": text, "expected": expected, "actual": actual, "correct": matched})
    return {
        "total": len(rows),
        "correct": correct,
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "details": rows,
    }


def evaluate_bundle(artifacts: dict[str, dict]) -> dict[str, Any]:
    issues = review_artifacts(artifacts)
    citations = artifacts.get("lesson_plan", {}).get("citations", [])
    invalid_citations = [
        item for item in citations
        if not all(item.get(key) for key in ("source_id", "chunk_id", "filename", "location", "quote"))
    ]
    return {
        "issue_count": len(issues),
        "fail_count": len([item for item in issues if item["severity"] == "fail"]),
        "warn_count": len([item for item in issues if item["severity"] == "warn"]),
        "citation_count": len(citations),
        "invalid_citation_count": len(invalid_citations),
        "issues": issues,
    }
