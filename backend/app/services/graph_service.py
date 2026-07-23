from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.generation import (
    design_lesson_blueprint,
    generate_exercises,
    generate_slide_outlines,
    materialize_lesson_artifacts,
    merge_blueprint_responses,
)
from app.ai.graph import NODES, build_langgraph, initial_node_state, review_quality
from app.ai.retriever import retrieve_evidence
from app.ai.schemas import Exercise, LessonBlueprint, LessonContext, SkillResponse
from app.ai.skills import SlideOutline
from app.ai.vector_store import ProjectVectorStore
from app.core.database import SessionLocal
from app.models import AITask, GraphRun, Project


ARTIFACT_TYPES = ("lesson_plan", "slide_deck", "speaker_notes", "exercise_set")
NODE_PROGRESS = {
    "analyze_sources": ("资料分析", 15),
    "design_lesson": ("教学设计", 35),
    "generate_slides": ("课件生成", 55),
    "generate_notes_exercises": ("讲稿与练习生成", 75),
    "review_quality": ("质量审校", 90),
    "human_confirm": ("等待教师确认", 95),
    "finalize": ("已完成", 100),
}


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _context_for(project: Project, task: AITask) -> LessonContext:
    snapshot = task.input_snapshot or {}
    return LessonContext(
        project_id=project.id,
        subject=project.subject,
        grade=project.grade,
        textbook_version=project.textbook_version,
        lesson_topic=project.lesson_topic,
        lesson_count=project.lesson_count,
        student_profile=project.student_profile,
        selected_source_ids=snapshot.get("selected_source_ids", []),
        teacher_requirements=snapshot.get("teacher_requirements") or project.teacher_requirements,
    )


def _initial_graph_state(project: Project, task: AITask, thread_id: str | None = None) -> dict[str, Any]:
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "subject": project.subject,
            "grade": project.grade,
            "lesson_topic": project.lesson_topic,
        },
        "context": _context_for(project, task).model_dump(mode="json"),
        "retrieval_summary": {},
        "blueprint": {},
        "artifacts": {},
        "citations": [],
        "issues": [],
        "current_node": "analyze_sources",
        "attempts": {},
        "warnings": [],
        "human_decision": None,
        "trace_id": thread_id or task.trace_id,
        "events": [],
        "cancelled": False,
        "failed": False,
        "error": "",
        "resume_from": "analyze_sources",
        "slide_outlines": [],
        "exercises": [],
        "skill_traces": [],
        "model": "rule-based-fallback",
        "degraded": False,
    }


class GraphRunCheckpointStore:
    """Persist complete LangGraph checkpoints in the existing GraphRun table."""

    def __init__(self, graph_id: str):
        self.graph_id = graph_id

    def load(self, project_id: str, trace_id: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            graph = db.get(GraphRun, self.graph_id)
            if not graph or graph.project_id != project_id or graph.thread_id != trace_id:
                return None
            return deepcopy(graph.state_snapshot or {})

    def save(self, project_id: str, trace_id: str, state: dict[str, Any]) -> None:
        with SessionLocal() as db:
            graph = db.get(GraphRun, self.graph_id)
            if not graph or graph.project_id != project_id or graph.thread_id != trace_id:
                raise RuntimeError("GRAPH_CHECKPOINT_NOT_FOUND")
            self._apply_state(graph, state)
            db.commit()

    def is_cancelled(self) -> bool:
        with SessionLocal() as db:
            graph = db.get(GraphRun, self.graph_id)
            if not graph:
                return True
            task = db.get(AITask, graph.task_id)
            return graph.status == "cancelled" or bool(task and task.status == "cancelled")

    def record_event(self, node_id: str, status: str, state: dict[str, Any]) -> None:
        with SessionLocal() as db:
            graph = db.get(GraphRun, self.graph_id)
            if not graph:
                raise RuntimeError("GRAPH_CHECKPOINT_NOT_FOUND")
            nodes = deepcopy(graph.nodes or initial_node_state())
            row = next((item for item in nodes if item["node_id"] == node_id), None)
            if row is None:
                row = {"node_id": node_id, "status": "pending", "attempt": 0, "issues": []}
                nodes.append(row)
            row["status"] = status
            if status == "running":
                row["attempt"] = int(row.get("attempt", 0)) + 1
            if node_id in {"review_quality", "human_confirm"}:
                row["issues"] = deepcopy(state.get("issues", []))
            graph.nodes = nodes
            self._apply_state(graph, state)
            if status == "cancelled":
                graph.status = "cancelled"
                graph.current_node = "cancelled"
            elif status == "awaiting_confirmation":
                graph.status = "awaiting_confirmation"
                graph.current_node = "human_confirm"
            elif status == "failed":
                graph.status = "failed"
            elif node_id == "finalize" and status == "succeeded":
                graph.status = "succeeded"
                graph.current_node = "finalize"
            else:
                graph.status = "running"
                graph.current_node = node_id
            task = db.get(AITask, graph.task_id)
            if task and task.status in {"pending", "running"}:
                stage, progress = NODE_PROGRESS[node_id]
                task.status = "running"
                task.stage = stage
                task.progress = progress
                task.started_at = task.started_at or datetime.utcnow()
            db.commit()

    @staticmethod
    def _apply_state(graph: GraphRun, state: dict[str, Any]) -> None:
        snapshot = _json_copy(state)
        graph.state_snapshot = snapshot
        graph.attempts = deepcopy(snapshot.get("attempts", {}))
        graph.issues = deepcopy(snapshot.get("issues", []))
        graph.human_decision = snapshot.get("human_decision")
        current = snapshot.get("current_node")
        if current:
            graph.current_node = current


def create_graph_run(
    db: Session,
    project: Project,
    task: AITask,
    *,
    thread_id: str | None = None,
    checkpoint_ref: str | None = None,
) -> GraphRun:
    state = _initial_graph_state(project, task, thread_id)
    graph = GraphRun(
        project_id=project.id,
        task_id=task.id,
        thread_id=state["trace_id"],
        checkpoint_ref=checkpoint_ref or f"task:{task.id}",
        attempt=1,
        status="pending",
        current_node="analyze_sources",
        attempts={},
        nodes=initial_node_state(),
        issues=[],
        state_snapshot=state,
    )
    db.add(graph)
    db.commit()
    db.refresh(graph)
    return graph


def _merge_citations(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for rows in groups:
        for row in rows:
            key = (str(row.get("source_id", "")), str(row.get("chunk_id", "")))
            merged[key] = row
    return list(merged.values())


def _skill_state_delta(state: dict[str, Any], responses: list[SkillResponse]) -> dict[str, Any]:
    traces = list(state.get("skill_traces", []))
    traces.extend(response.trace.model_dump(mode="json") for response in responses)
    models = [item["model"] for item in traces if item.get("model") != "rule-based-fallback"]
    warnings = list(state.get("warnings", []))
    warnings.extend(warning for response in responses for warning in response.warnings)
    return {
        "skill_traces": traces,
        "model": models[0] if models else "rule-based-fallback",
        "degraded": bool(state.get("degraded")) or any(response.degraded for response in responses),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _graph_handlers(store: ProjectVectorStore) -> dict[str, Any]:
    def context(state: dict[str, Any]) -> LessonContext:
        return LessonContext.model_validate(state["context"])

    def analyze_sources(state: dict[str, Any]) -> dict[str, Any]:
        lesson = context(state)
        evidence = retrieve_evidence(
            lesson,
            f"{lesson.grade}{lesson.subject}《{lesson.lesson_topic}》课程标准、教材知识与教学要求",
            store=store,
        )
        citations = [item.model_dump(mode="json") for item in evidence.citations]
        return {
            "retrieval_summary": {
                "count": len(evidence.rows),
                "sufficient": evidence.sufficient,
                "conflicts": evidence.conflicts,
                "sources": [
                    {
                        "source_id": row["source_id"],
                        "chunk_id": row["chunk_id"],
                        "filename": row["filename"],
                        "location": row["location"],
                        "score": row["score"],
                    }
                    for row in evidence.rows
                ],
            },
            "citations": _merge_citations(state.get("citations", []), citations),
            "warnings": list(dict.fromkeys(list(state.get("warnings", [])) + evidence.warnings)),
        }

    def design_lesson(state: dict[str, Any]) -> dict[str, Any]:
        blueprint, responses = design_lesson_blueprint(
            context(state),
            store=store,
            trace_id=state["trace_id"],
        )
        delta = _skill_state_delta(state, responses)
        delta.update(
            {
                "blueprint": blueprint.model_dump(mode="json"),
                "citations": _merge_citations(
                    state.get("citations", []),
                    [item.model_dump(mode="json") for item in blueprint.citations],
                ),
                "warnings": list(dict.fromkeys(delta["warnings"] + blueprint.warnings)),
            }
        )
        return delta

    def generate_slides(state: dict[str, Any]) -> dict[str, Any]:
        blueprint = LessonBlueprint.model_validate(state["blueprint"])
        outlines, response = generate_slide_outlines(
            context(state),
            blueprint,
            store=store,
            trace_id=state["trace_id"],
        )
        blueprint = merge_blueprint_responses(blueprint, [response])
        delta = _skill_state_delta(state, [response])
        delta.update(
            {
                "blueprint": blueprint.model_dump(mode="json"),
                "slide_outlines": [item.model_dump(mode="json") for item in outlines],
                "citations": _merge_citations(
                    state.get("citations", []),
                    [item.model_dump(mode="json") for item in blueprint.citations],
                ),
                "warnings": list(dict.fromkeys(delta["warnings"] + blueprint.warnings)),
            }
        )
        if state.get("exercises"):
            exercises = [Exercise.model_validate(item) for item in state["exercises"]]
            delta["artifacts"] = materialize_lesson_artifacts(
                context(state),
                blueprint,
                outlines,
                exercises,
            )
        return delta

    def generate_notes_exercises(state: dict[str, Any]) -> dict[str, Any]:
        blueprint = LessonBlueprint.model_validate(state["blueprint"])
        outlines = [SlideOutline.model_validate(item) for item in state["slide_outlines"]]
        exercises, response, links_changed = generate_exercises(
            context(state),
            blueprint,
            store=store,
            trace_id=state["trace_id"],
        )
        blueprint = merge_blueprint_responses(blueprint, [response])
        if links_changed:
            blueprint.warnings.append("已按教学目标自动修正练习中的目标编号关联，请教师复核。")
        delta = _skill_state_delta(state, [response])
        delta.update(
            {
                "blueprint": blueprint.model_dump(mode="json"),
                "exercises": [item.model_dump(mode="json") for item in exercises],
                "artifacts": materialize_lesson_artifacts(
                    context(state),
                    blueprint,
                    outlines,
                    exercises,
                ),
                "citations": _merge_citations(
                    state.get("citations", []),
                    [item.model_dump(mode="json") for item in blueprint.citations],
                ),
                "warnings": list(dict.fromkeys(delta["warnings"] + blueprint.warnings)),
            }
        )
        return delta

    def review(state: dict[str, Any]) -> dict[str, Any]:
        return {"issues": review_quality(state.get("artifacts", {}), trace_id=state["trace_id"])}

    def human(state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("human_decision")
        return {
            "human_decision": decision,
            "cancelled": decision == "cancel",
        }

    def finalize(state: dict[str, Any]) -> dict[str, Any]:
        if set(state.get("artifacts", {})) != set(ARTIFACT_TYPES):
            raise RuntimeError("四类备课产物不完整，不能完成流程")
        return {"failed": False, "error": ""}

    return {
        "analyze_sources": analyze_sources,
        "design_lesson": design_lesson,
        "generate_slides": generate_slides,
        "generate_notes_exercises": generate_notes_exercises,
        "review_quality": review,
        "human_confirm": human,
        "finalize": finalize,
    }


def _artifact_hash(artifacts: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _persist_graph_result(graph_id: str, state: dict[str, Any]) -> dict[str, Any]:
    from app.services.artifact_service import save_version

    artifacts = state.get("artifacts", {})
    with SessionLocal() as db:
        graph = db.get(GraphRun, graph_id)
        if not graph:
            raise RuntimeError("GRAPH_NOT_FOUND")
        task = db.get(AITask, graph.task_id)
        if not task:
            raise RuntimeError("TASK_NOT_FOUND")
        if state.get("cancelled"):
            graph.status = "cancelled"
            graph.current_node = "cancelled"
            if task.status in {"pending", "running"}:
                task.status = "cancelled"
                task.stage = "用户已取消"
                task.finished_at = datetime.utcnow()
            db.commit()
            return state
        if state.get("current_node") == "human_confirm" and artifacts:
            digest = _artifact_hash(artifacts)
            if digest != state.get("persisted_artifact_hash"):
                citation_rows = list(state.get("citations", []))
                warnings = list(state.get("warnings", []))
                if state.get("degraded"):
                    warnings = list(
                        dict.fromkeys(
                            warnings
                            + ["当前产物包含规则降级内容，不代表 DeepSeek 生成成功，必须由教师确认。"]
                        )
                    )
                first = None
                for artifact_type in ARTIFACT_TYPES:
                    artifact = save_version(
                        db,
                        graph.project_id,
                        artifact_type,
                        artifacts[artifact_type],
                        citation_rows,
                        warnings,
                        change_type="graph_generated",
                    )
                    first = first or artifact.id
                state["persisted_artifact_hash"] = digest
                task.result_artifact_id = first or task.result_artifact_id
            task.result_snapshot = {
                "kind": "full_lesson",
                "artifact_types": list(ARTIFACT_TYPES),
                "model": state.get("model", "rule-based-fallback"),
                "degraded": bool(state.get("degraded")),
                "trace": (state.get("skill_traces") or [None])[-1],
                "graph_id": graph.id,
            }
            task.status = "succeeded"
            task.stage = "已生成，等待教师确认"
            task.progress = 100
            task.finished_at = datetime.utcnow()
            graph.status = "awaiting_confirmation"
            graph.current_node = "human_confirm"
        elif state.get("current_node") == "finalize":
            graph.status = "succeeded"
            graph.current_node = "finalize"
            task.status = "succeeded"
            task.stage = "已完成"
            task.progress = 100
            task.finished_at = task.finished_at or datetime.utcnow()
        elif state.get("failed") and not artifacts:
            task.status = "failed"
            task.stage = "生成失败"
            task.error_code = "GRAPH_NODE_FAILED"
            task.error_message = str(state.get("error", "LangGraph 节点执行失败"))[:500]
            task.finished_at = datetime.utcnow()
        db.commit()
    return state


def execute_graph_run(
    graph_id: str,
    *,
    resume_from: str | None = None,
    human_decision: str | None = None,
    reset_failure: bool = False,
) -> dict[str, Any] | None:
    checkpoint = GraphRunCheckpointStore(graph_id)
    with SessionLocal() as db:
        graph = db.get(GraphRun, graph_id)
        if not graph:
            return None
        task = db.get(AITask, graph.task_id)
        project = db.get(Project, graph.project_id)
        if not task or not project:
            raise RuntimeError("GRAPH_CONTEXT_NOT_FOUND")
        state = _initial_graph_state(project, task, graph.thread_id)
        state.update(checkpoint.load(project.id, graph.thread_id) or {})
        if not state.get("context"):
            state["context"] = _context_for(project, task).model_dump(mode="json")
        state["trace_id"] = graph.thread_id
        state["resume_from"] = (
            resume_from or state.get("resume_from") or state.get("current_node") or "analyze_sources"
        )
        if human_decision is not None:
            state["human_decision"] = human_decision
        if reset_failure:
            state["cancelled"] = False
            state["failed"] = False
            state["error"] = ""
        graph.status = "running"
        graph.current_node = str(state["resume_from"])
        graph.human_decision = state.get("human_decision")
        graph.state_snapshot = _json_copy(state)
        db.commit()

    store = ProjectVectorStore()
    try:
        runnable = build_langgraph(
            _graph_handlers(store),
            on_node_event=checkpoint.record_event,
            cancel_check=checkpoint.is_cancelled,
        )
        if runnable is None:
            raise RuntimeError("缺少 langgraph 依赖")
        result = dict(runnable.invoke(state))
    finally:
        store.close()
    result = _persist_graph_result(graph_id, result)
    checkpoint.save(result["context"]["project_id"], result["trace_id"], result)
    return result


def start_task_graph(task_id: str) -> None:
    graph_id: str | None = None
    try:
        with SessionLocal() as db:
            task = db.get(AITask, task_id)
            if not task or task.status == "cancelled":
                return
            project = db.get(Project, task.project_id)
            if not project:
                task.status = "failed"
                task.error_code = "PROJECT_NOT_FOUND"
                task.error_message = "项目不存在"
                task.finished_at = datetime.utcnow()
                db.commit()
                return
            task.status = "running"
            task.stage = "启动 LangGraph"
            task.progress = 5
            task.started_at = task.started_at or datetime.utcnow()
            graph = create_graph_run(db, project, task)
            graph_id = graph.id
        execute_graph_run(graph_id, resume_from="analyze_sources")
    except Exception as exc:
        with SessionLocal() as db:
            task = db.get(AITask, task_id)
            if task:
                task.status = "failed"
                task.stage = "生成失败"
                task.error_code = getattr(exc, "code", "INTERNAL_ERROR")
                task.error_message = str(exc)[:500]
                task.finished_at = datetime.utcnow()
            if graph_id:
                graph = db.get(GraphRun, graph_id)
                if graph and graph.status != "cancelled":
                    graph.status = "failed"
            db.commit()


def resume_graph_run(graph_id: str, *, resume_from: str | None = None) -> dict[str, Any] | None:
    return execute_graph_run(graph_id, resume_from=resume_from, reset_failure=True)


def decide_graph(graph_id: str, decision: str) -> dict[str, Any] | None:
    return execute_graph_run(
        graph_id,
        resume_from="human_confirm",
        human_decision=decision,
        reset_failure=True,
    )
