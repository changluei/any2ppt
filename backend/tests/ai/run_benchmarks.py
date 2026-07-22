from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ai.embeddings import HashEmbeddingProvider
from app.ai.evaluation import GoldenQuery, evaluate_bundle, evaluate_retrieval, evaluate_router
from app.ai.generation import generate_lesson_bundle
from app.ai.graph import build_langgraph
from app.ai.ingestion import Chunk
from app.ai.schemas import LessonContext
from app.ai.skills import registry
from app.ai.vector_store import ProjectVectorStore


FIXTURE = Path(__file__).parent / "fixtures" / "golden_retrieval.json"
ROUTER_CASES = [
    ("请解读课程标准", "course_standard_interpretation"),
    ("找出本课课标依据", "course_standard_interpretation"),
    ("设计可评价的教学目标", "learning_objectives"),
    ("结合学情分析重难点", "learning_objectives"),
    ("设计课堂活动", "teaching_activities"),
    ("安排教学流程", "teaching_activities"),
    ("规划课件和讲稿", "slide_narrative"),
    ("生成幻灯片", "slide_narrative"),
    ("设计分层练习", "exercise_assessment"),
    ("帮我看看", None),
]


def _signature(artifacts: dict) -> str:
    payload = json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run() -> dict:
    data = json.loads(FIXTURE.read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="lessondeck-benchmark-") as directory:
        # Golden scoring uses the deterministic local backend; a separate test covers real Chroma persistence.
        store = ProjectVectorStore(Path(directory), HashEmbeddingProvider(256), force_json=True)
        for row in data:
            if row["source_id"]:
                store.add_documents(
                    "golden-project",
                    row["source_id"],
                    row["filename"],
                    [Chunk(f"chunk-{row['source_id']}", row["content"], row["category"], f"hash-{row['source_id']}")],
                )
        retrieval = evaluate_retrieval(
            store,
            [GoldenQuery("golden-project", row["query"], row["source_id"]) for row in data],
            top_k=3,
            min_score=0.12,
        )
        context = LessonContext(
            project_id="golden-project",
            subject="科学",
            grade="四年级",
            lesson_topic="水的蒸发",
        )
        first = generate_lesson_bundle(context, store=store, trace_id="benchmark-run-1")
        second = generate_lesson_bundle(context, store=store, trace_id="benchmark-run-2")
        quality = evaluate_bundle(first.artifacts)
        report = {
            "retrieval": {
                "total": retrieval["total"],
                "top3_hit_rate": retrieval["top3_hit_rate"],
                "empty_retrievals": retrieval["empty_retrievals"],
            },
            "router": evaluate_router(ROUTER_CASES),
            "skills": {"count": len(registry()), "schemas_complete": all(item["input_schema"] and item["output_schema"] for item in registry())},
            "bundle": {
                "slides": len(first.artifacts["slide_deck"]["slides"]),
                "notes": len(first.artifacts["speaker_notes"]["notes"]),
                "exercise_levels": sorted(item["level"] for item in first.artifacts["exercise_set"]["exercises"]),
                "citation_count": len(first.citations),
                "degraded": first.degraded,
                "quality_failures": quality["fail_count"],
                "two_run_structure_stable": _signature(first.artifacts) == _signature(second.artifacts),
            },
            "langgraph": {"compiled": build_langgraph() is not None, "bounded_repair_attempts": 2},
        }
        store.close()
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", "utf-8")
    print(payload)


if __name__ == "__main__":
    main()
