from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any

from app.ai.graph import NODES, build_langgraph, initial_node_state, review_quality
from app.core.database import SessionLocal
from app.models import AITask, GraphRun, LessonArtifact


def _latest_artifacts(db, project_id: str) -> dict[str, dict[str, Any]]:
    rows = db.query(LessonArtifact).filter_by(project_id=project_id).all()
    return {
        artifact.type: artifact.versions[-1].content
        for artifact in rows
        if artifact.versions
    }


def _node_rows(events: list[dict[str, Any]], attempts: dict[str, int], waiting: bool) -> list[dict[str, Any]]:
    rows = initial_node_state()
    completed = {event.get("node_id") for event in events if event.get("status") == "succeeded"}
    failed = {event.get("node_id") for event in events if event.get("status") == "failed"}
    for row in rows:
        node_id = row["node_id"]
        row["attempt"] = attempts.get(node_id, 1 if node_id in completed else 0)
        if node_id in failed:
            row["status"] = "failed"
        elif node_id in completed:
            row["status"] = "succeeded"
        if node_id == "human_confirm" and waiting:
            row["status"] = "running"
    return rows


def execute_graph_run(graph_id: str) -> None:
    """Execute the production LangGraph and persist its interrupt checkpoint in MySQL."""
    db = SessionLocal()
    graph = db.get(GraphRun, graph_id)
    if not graph or graph.status == "cancelled":
        db.close()
        return
    started = perf_counter()
    try:
        task = db.get(AITask, graph.task_id)
        artifacts = _latest_artifacts(db, graph.project_id)
        if not task or set(artifacts) != {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"}:
            raise RuntimeError("完整产物尚未就绪，无法启动工作流")

        def analyze(state):
            return {
                "retrieval_summary": {
                    "selected_source_ids": task.input_snapshot.get("selected_source_ids", []),
                    "source_count": len(task.input_snapshot.get("selected_source_ids", [])),
                }
            }

        def design(state):
            return {"blueprint": artifacts["lesson_plan"], "artifacts": artifacts}

        def slides(state):
            return {"artifacts": state.get("artifacts", artifacts)}

        def notes_exercises(state):
            return {"artifacts": state.get("artifacts", artifacts)}

        def review(state):
            current = state.get("artifacts", artifacts)
            return {"artifacts": current, "issues": review_quality(current, trace_id=graph.thread_id)}

        handlers = {
            "analyze_sources": analyze,
            "design_lesson": design,
            "generate_slides": slides,
            "generate_notes_exercises": notes_exercises,
            "review_quality": review,
            "human_confirm": lambda state: {},
            "finalize": lambda state: {},
        }
        compiled = build_langgraph(handlers)
        if compiled is None:
            raise RuntimeError("LangGraph 依赖不可用")
        initial = {
            "project": {"id": graph.project_id},
            "artifacts": artifacts,
            "trace_id": graph.thread_id,
            "attempts": graph.attempts or {},
            "events": [],
            "warnings": [],
        }
        state = compiled.invoke(initial, config={"recursion_limit": 30})
        events = state.get("events", [])
        graph.attempts = state.get("attempts", {})
        graph.issues = state.get("issues", [])
        graph.current_node = "human_confirm"
        graph.status = "awaiting_confirmation"
        graph.nodes = _node_rows(events, graph.attempts, waiting=True)
        graph.state_snapshot = {
            **state,
            "checkpointed_at": datetime.utcnow().isoformat(),
            "elapsed_ms": int((perf_counter() - started) * 1000),
        }
        db.commit()
    except Exception as exc:
        db.rollback()
        graph = db.get(GraphRun, graph_id)
        if graph:
            graph.status = "failed"
            graph.current_node = "human_confirm"
            graph.issues = [{
                "issue_type": "workflow_error",
                "target_id": "human_confirm",
                "severity": "fail",
                "suggestion": str(exc)[:300],
            }]
            graph.state_snapshot = {
                **(graph.state_snapshot or {}),
                "error": str(exc)[:500],
                "failed_at": datetime.utcnow().isoformat(),
            }
            db.commit()
    finally:
        db.close()


def finalize_graph(graph_id: str, decision: str) -> GraphRun | None:
    db = SessionLocal()
    try:
        graph = db.get(GraphRun, graph_id)
        if not graph:
            return None
        graph.human_decision = decision
        if decision == "accept":
            graph.status = "succeeded"
            graph.current_node = "finalize"
            rows = list(graph.nodes or [])
            for row in rows:
                if row["node_id"] == "human_confirm":
                    row["status"] = "succeeded"
                if row["node_id"] == "finalize":
                    row["status"] = "succeeded"
                    row["attempt"] = max(1, row.get("attempt", 0))
            graph.nodes = rows
        elif decision == "cancel":
            graph.status = "cancelled"
            graph.current_node = "cancelled"
        else:
            graph.status = "needs_revision"
            graph.current_node = (graph.state_snapshot or {}).get("repair_scope") or "review_quality"
        db.commit()
        db.refresh(graph)
        db.expunge(graph)
        return graph
    finally:
        db.close()


def repair_graph_run(graph_id: str) -> None:
    """Apply the reviewer suggestion to the smallest stable block, then re-run review."""
    db = SessionLocal()
    try:
        graph = db.get(GraphRun, graph_id)
        if not graph or graph.status == "cancelled":
            return
        issue = next((item for item in graph.issues if item.get("severity") == "fail"), None)
        issue = issue or next(iter(graph.issues or []), None)
        if not issue:
            graph.status = "awaiting_confirmation"
            graph.current_node = "human_confirm"
            db.commit()
            return
        target_id = issue.get("target_id", "")
        issue_type = issue.get("issue_type", "")
        if target_id.startswith("SLIDE-") and issue_type in {"missing_note", "orphan_note"}:
            artifact_type, target_type = "speaker_notes", "note"
        elif target_id.startswith("SLIDE-"):
            artifact_type, target_type = "slide_deck", "slide"
        elif target_id.startswith("EX-"):
            artifact_type, target_type = "exercise_set", "exercise"
        else:
            artifact_type, target_type = "lesson_plan", "stages"
        artifact = db.query(LessonArtifact).filter_by(
            project_id=graph.project_id, type=artifact_type
        ).first()
        if not artifact or not artifact.versions:
            raise RuntimeError("无法定位需要返修的产物")
        if target_type == "stages":
            rows = artifact.versions[-1].content.get("stages", [])
            if not rows:
                raise RuntimeError("无法定位需要返修的教学环节")
            target_id = rows[0]["id"]
        from app.services.artifact_service import revise_artifact

        revise_artifact(
            db,
            artifact,
            artifact.current_version_no,
            target_type,
            target_id,
            issue.get("suggestion") or "按质量检查建议修正",
            sync_related=target_type == "slide",
        )
        graph = db.get(GraphRun, graph_id)
        graph.attempt += 1
        graph.human_decision = "revise"
        graph.status = "running"
        graph.current_node = target_type
        db.commit()
    except Exception as exc:
        db.rollback()
        graph = db.get(GraphRun, graph_id)
        if graph:
            graph.status = "failed"
            graph.state_snapshot = {**(graph.state_snapshot or {}), "repair_error": str(exc)[:500]}
            db.commit()
        return
    finally:
        db.close()
    execute_graph_run(graph_id)
