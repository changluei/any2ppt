from __future__ import annotations

import json
from typing import Any, Callable, Literal, Protocol, TypedDict

from pydantic import BaseModel, Field

from .exceptions import AIConfigurationError, AIError
from .llm_client import DeepSeekClient


NODES = [
    "analyze_sources",
    "design_lesson",
    "generate_slides",
    "generate_notes_exercises",
    "review_quality",
    "human_confirm",
    "finalize",
]
MAX_REPAIR_ATTEMPTS = 2


class CheckpointAdapter(Protocol):
    """Member 3 can implement this protocol with the existing MySQL GraphRun model."""

    def load(self, project_id: str, trace_id: str) -> dict[str, Any] | None: ...

    def save(self, project_id: str, trace_id: str, state: dict[str, Any]) -> None: ...


class ReviewerIssue(BaseModel):
    issue_type: str
    target_id: str
    severity: Literal["warn", "fail"]
    suggestion: str


class ModelReviewOutput(BaseModel):
    issues: list[ReviewerIssue] = Field(default_factory=list)


class LessonState(TypedDict, total=False):
    project: dict[str, Any]
    context: dict[str, Any]
    retrieval_summary: dict[str, Any]
    blueprint: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    citations: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    current_node: str
    attempts: dict[str, int]
    warnings: list[str]
    human_decision: str | None
    trace_id: str
    events: list[dict[str, Any]]
    cancelled: bool
    repair_scope: str
    failed: bool
    error: str


def _issue(issue_type: str, target_id: str, severity: str, suggestion: str) -> dict:
    return {
        "issue_type": issue_type,
        "target_id": target_id,
        "severity": severity,
        "suggestion": suggestion,
    }


def review_artifacts(artifacts: dict[str, dict]) -> list[dict]:
    issues: list[dict] = []
    plan = artifacts.get("lesson_plan", {})
    slides = artifacts.get("slide_deck", {}).get("slides", [])
    notes = artifacts.get("speaker_notes", {}).get("notes", [])
    exercises = artifacts.get("exercise_set", {}).get("exercises", [])

    objectives = plan.get("objectives", [])
    objective_ids = {item.get("id") for item in objectives if item.get("id")}
    core_ids = {item.get("id") for item in objectives if item.get("id") and item.get("core", True)}
    stages = plan.get("stages", plan.get("activities", []))
    assessments = plan.get("assessments", [])
    activity_coverage = {oid for stage in stages for oid in stage.get("objective_ids", [])}
    assessment_coverage = {oid for item in assessments for oid in item.get("objective_ids", [])}
    exercise_coverage = {oid for item in exercises for oid in item.get("objective_ids", [])}

    for objective_id in sorted(core_ids - activity_coverage):
        issues.append(_issue("objective_without_activity", objective_id, "fail", "为核心目标增加对应课堂活动"))
    for objective_id in sorted(core_ids - (assessment_coverage | exercise_coverage)):
        issues.append(_issue("objective_unassessed", objective_id, "fail", "为核心目标增加评价或练习"))
    referenced_ids = activity_coverage | assessment_coverage | exercise_coverage
    for objective_id in sorted(referenced_ids - objective_ids):
        issues.append(_issue("unknown_objective", objective_id, "fail", "改为教学设计中存在的目标编号"))

    total_minutes = sum(int(stage.get("time_minutes", 0) or 0) for stage in stages)
    if not 35 <= total_minutes <= 50:
        issues.append(_issue("lesson_time", "lesson_plan", "warn", "将单课时总时长调整到 35—50 分钟"))

    if not 12 <= len(slides) <= 18:
        issues.append(_issue("slide_count", "slide_deck", "fail", "课件页数应保持在 12—18 页"))
    slide_ids = [slide.get("slide_id") for slide in slides]
    stage_ids = {stage.get("id") for stage in stages if stage.get("id")}
    if len(set(slide_ids)) != len(slide_ids):
        issues.append(_issue("duplicate_slide_id", "slide_deck", "fail", "每页必须使用唯一且稳定的 slide_id"))
    note_ids = {note.get("slide_id") for note in notes}
    for slide in slides:
        slide_id = slide.get("slide_id") or "unknown-slide"
        for objective_id in set(slide.get("objective_ids", [])) - objective_ids:
            issues.append(_issue("slide_unknown_objective", slide_id, "fail", f"课件页引用了未知目标 {objective_id}"))
        if stage_ids and slide.get("teaching_stage") not in stage_ids:
            issues.append(_issue("slide_unknown_stage", slide_id, "fail", "课件页需要绑定有效教学环节"))
        if slide_id not in note_ids:
            issues.append(_issue("missing_note", slide_id, "fail", "补充与该页对应的逐页讲稿"))
        markdown = slide.get("markdown", "")
        if len(markdown) > 600 or len([line for line in markdown.splitlines() if line.strip()]) > 12:
            issues.append(_issue("slide_density", slide_id, "warn", "拆分页面或精简投影文字"))
    for orphan in sorted(note_ids - set(slide_ids)):
        issues.append(_issue("orphan_note", orphan or "unknown-note", "fail", "删除或重新绑定无对应课件页的讲稿"))

    levels = {item.get("level") for item in exercises}
    for level in ("基础", "巩固", "提高"):
        if level not in levels:
            issues.append(_issue("missing_exercise_level", level, "fail", f"增加{level}层次练习"))
    for exercise in exercises:
        exercise_id = exercise.get("exercise_id") or "unknown-exercise"
        if not exercise.get("answer") or not exercise.get("explanation"):
            issues.append(_issue("exercise_answer_missing", exercise_id, "fail", "补充教师版答案和解析"))
        if exercise.get("source") == "generated" and not exercise.get("needs_teacher_review"):
            issues.append(_issue("generated_exercise_unmarked", exercise_id, "fail", "原创练习必须标记需教师确认"))
        difficulty = int(exercise.get("difficulty", 0) or 0)
        if not 1 <= difficulty <= 5:
            issues.append(_issue("exercise_difficulty", exercise_id, "warn", "将练习难度调整到 1—5"))

    citations = plan.get("citations", []) or artifacts.get("slide_deck", {}).get("citations", [])
    if not citations:
        issues.append(_issue("citation_insufficient", "artifacts", "warn", "当前没有资料引用，界面应明确提示通用建议"))
    for citation in citations:
        if not all(citation.get(key) for key in ("source_id", "chunk_id", "filename", "location", "quote")):
            issues.append(_issue("citation_incomplete", citation.get("chunk_id", "citation"), "fail", "补齐真实来源字段或删除该引用"))

    return issues


def review_quality(artifacts: dict[str, dict], *, llm=None, trace_id: str | None = None) -> list[dict]:
    """Deterministic rules are authoritative; a structured model reviewer may add pedagogical warnings."""
    deterministic = review_artifacts(artifacts)
    client = llm or DeepSeekClient()
    if getattr(client, "configured", True) is False:
        return deterministic
    allowed_targets = {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set", "artifacts"}
    allowed_targets.update(item.get("id") for item in artifacts.get("lesson_plan", {}).get("objectives", []))
    allowed_targets.update(item.get("slide_id") for item in artifacts.get("slide_deck", {}).get("slides", []))
    allowed_targets.update(item.get("exercise_id") for item in artifacts.get("exercise_set", {}).get("exercises", []))
    summary = {
        "lesson_plan": artifacts.get("lesson_plan", {}),
        "slides": artifacts.get("slide_deck", {}).get("slides", []),
        "notes": artifacts.get("speaker_notes", {}).get("notes", []),
        "exercises": artifacts.get("exercise_set", {}).get("exercises", []),
    }
    try:
        output, _ = client.invoke_structured(
            "你是小学教学质量审校员。确定性规则结果不可删除；只补充需要教师判断的问题。禁止编造事实或来源。只输出 JSON。",
            f"现有规则问题：{json.dumps(deterministic, ensure_ascii=False)}\n待审校产物：{json.dumps(summary, ensure_ascii=False)[:24000]}",
            ModelReviewOutput,
            trace_id=trace_id,
        )
    except AIConfigurationError:
        return deterministic
    except AIError:
        return deterministic + [_issue("reviewer_unavailable", "artifacts", "warn", "模型审校暂时不可用，已保留确定性规则结果")]
    combined = list(deterministic)
    existing = {(item["issue_type"], item["target_id"]) for item in combined}
    for item in output.issues:
        target = item.target_id if item.target_id in allowed_targets else "artifacts"
        key = (item.issue_type, target)
        if key not in existing:
            combined.append(_issue(item.issue_type, target, item.severity, item.suggestion))
            existing.add(key)
    return combined


def initial_node_state() -> list[dict[str, Any]]:
    return [{"node_id": node, "status": "pending", "attempt": 0, "issues": []} for node in NODES]


def _repair_scope(issues: list[dict]) -> str:
    failing = {item["issue_type"] for item in issues if item.get("severity") == "fail"}
    if failing & {"objective_without_activity", "objective_unassessed", "unknown_objective"}:
        return "design"
    if failing & {"slide_count", "duplicate_slide_id", "slide_density", "slide_unknown_objective", "slide_unknown_stage"}:
        return "slides"
    if failing & {
        "missing_note", "orphan_note", "missing_exercise_level", "exercise_answer_missing",
        "generated_exercise_unmarked", "exercise_difficulty",
    }:
        return "notes_exercises"
    return "human"


def route_after_review(state: LessonState) -> str:
    if state.get("cancelled"):
        return "cancelled"
    if state.get("failed"):
        return "human_confirm"
    scope = state.get("repair_scope") or _repair_scope(state.get("issues", []))
    target = {
        "design": "design_lesson",
        "slides": "generate_slides",
        "notes_exercises": "generate_notes_exercises",
    }.get(scope)
    if target and state.get("attempts", {}).get(target, 0) < MAX_REPAIR_ATTEMPTS:
        return target
    return "human_confirm"


def route_after_slides(state: LessonState) -> str:
    if state.get("cancelled"):
        return "cancelled"
    if state.get("failed"):
        return "human_confirm"
    return "review_quality" if state.get("repair_scope") == "slides" else "generate_notes_exercises"


def _continue_after_step(state: LessonState, next_node: str) -> str:
    if state.get("cancelled"):
        return "cancelled"
    if state.get("failed"):
        return "human_confirm"
    return next_node


def route_after_human(state: LessonState) -> str:
    decision = state.get("human_decision")
    if decision == "accept":
        return "finalize"
    if decision == "revise":
        scope = state.get("repair_scope") or "design"
        return {
            "slides": "generate_slides",
            "notes_exercises": "generate_notes_exercises",
        }.get(scope, "design_lesson")
    return "cancelled"


def _event(state: LessonState, node: str, status: str = "succeeded") -> list[dict[str, Any]]:
    return state.get("events", []) + [{"node_id": node, "status": status, "trace_id": state.get("trace_id", "")}]


def build_langgraph(node_handlers: dict[str, Callable[[LessonState], dict[str, Any]]] | None = None):
    """Build the real conditional graph; handlers let the service inject generation/checkpoint work."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    handlers = node_handlers or {}
    builder = StateGraph(LessonState)

    def make_node(node_id: str):
        def execute(state: LessonState) -> dict[str, Any]:
            if state.get("cancelled"):
                return {"current_node": node_id, "events": _event(state, node_id, "cancelled")}
            try:
                result = dict(handlers[node_id](state)) if node_id in handlers else {}
            except Exception as exc:
                result = {
                    "failed": True,
                    "error": str(exc)[:500],
                    "repair_scope": "human",
                    "issues": [_issue("node_exception", node_id, "fail", "节点执行失败，请重试或转人工确认")],
                    "warnings": state.get("warnings", []) + [f"{node_id} 执行失败，流程已停止自动返修。"],
                    "events": _event(state, node_id, "failed"),
                }
            attempts = dict(state.get("attempts", {}))
            if node_id in {"design_lesson", "generate_slides", "generate_notes_exercises"}:
                attempts[node_id] = attempts.get(node_id, 0) + 1
            result.setdefault("attempts", attempts)
            result.setdefault("current_node", node_id)
            result.setdefault("events", _event(state, node_id))
            if node_id == "review_quality":
                issues = result.get("issues") or state.get("issues") or review_artifacts(result.get("artifacts", state.get("artifacts", {})))
                result["issues"] = issues
                result["repair_scope"] = _repair_scope(issues)
            if node_id == "human_confirm" and not state.get("human_decision"):
                result["events"] = _event(state, node_id, "awaiting_confirmation")
            return result

        return execute

    for node_id in NODES:
        builder.add_node(node_id, make_node(node_id))
    builder.set_entry_point("analyze_sources")
    builder.add_conditional_edges(
        "analyze_sources",
        lambda state: _continue_after_step(state, "design_lesson"),
        {"design_lesson": "design_lesson", "human_confirm": "human_confirm", "cancelled": END},
    )
    builder.add_conditional_edges(
        "design_lesson",
        lambda state: _continue_after_step(state, "generate_slides"),
        {"generate_slides": "generate_slides", "human_confirm": "human_confirm", "cancelled": END},
    )
    builder.add_conditional_edges(
        "generate_slides",
        route_after_slides,
        {"generate_notes_exercises": "generate_notes_exercises", "review_quality": "review_quality", "human_confirm": "human_confirm", "cancelled": END},
    )
    builder.add_conditional_edges(
        "generate_notes_exercises",
        lambda state: _continue_after_step(state, "review_quality"),
        {"review_quality": "review_quality", "human_confirm": "human_confirm", "cancelled": END},
    )
    builder.add_conditional_edges(
        "review_quality",
        route_after_review,
        {
            "design_lesson": "design_lesson",
            "generate_slides": "generate_slides",
            "generate_notes_exercises": "generate_notes_exercises",
            "human_confirm": "human_confirm",
            "cancelled": END,
        },
    )
    builder.add_conditional_edges(
        "human_confirm",
        route_after_human,
        {
            "design_lesson": "design_lesson",
            "generate_slides": "generate_slides",
            "generate_notes_exercises": "generate_notes_exercises",
            "finalize": "finalize",
            "cancelled": END,
        },
    )
    builder.add_edge("finalize", END)
    return builder.compile(interrupt_before=["human_confirm"])
