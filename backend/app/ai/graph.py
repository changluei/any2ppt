from dataclasses import dataclass, field
from typing import Any


NODES = ["analyze_sources", "design_lesson", "generate_slides", "generate_notes_exercises", "review_quality", "human_confirm", "finalize"]


def review_artifacts(artifacts: dict[str, dict]) -> list[dict]:
    issues = []
    plan = artifacts.get("lesson_plan", {})
    slides = artifacts.get("slide_deck", {}).get("slides", [])
    notes = artifacts.get("speaker_notes", {}).get("notes", [])
    exercises = artifacts.get("exercise_set", {}).get("exercises", [])
    objective_ids = {o.get("id") for o in plan.get("objectives", [])}
    covered = {oid for e in exercises for oid in e.get("objective_ids", [])}
    for oid in objective_ids - covered:
        issues.append({"issue_type": "objective_unassessed", "target_id": oid, "severity": "fail", "suggestion": "为该目标增加评价或练习"})
    note_ids = {n.get("slide_id") for n in notes}
    for slide in slides:
        sid = slide.get("slide_id")
        if sid not in note_ids:
            issues.append({"issue_type": "missing_note", "target_id": sid, "severity": "fail", "suggestion": "补充对应讲稿"})
        if len(slide.get("markdown", "")) > 800:
            issues.append({"issue_type": "slide_density", "target_id": sid, "severity": "warn", "suggestion": "拆分页面或精简文字"})
    total = sum(stage.get("time_minutes", 0) for stage in plan.get("stages", []))
    if not 35 <= total <= 50:
        issues.append({"issue_type": "lesson_time", "target_id": "lesson_plan", "severity": "warn", "suggestion": "将总时长调整到单课时范围"})
    return issues


def initial_node_state() -> list[dict[str, Any]]:
    return [{"node_id": node, "status": "pending", "attempt": 0, "issues": []} for node in NODES]


def build_langgraph():
    """构建真实 LangGraph；基础安装未包含 AI 扩展时由服务层状态机降级。"""
    try:
        from langgraph.graph import StateGraph, END
        from typing_extensions import TypedDict
    except ImportError:
        return None

    class LessonState(TypedDict, total=False):
        current_node: str
        issues: list[dict]
        events: list[dict]
        human_decision: str

    builder = StateGraph(LessonState)
    for node_id in NODES:
        def advance(state, current=node_id):
            return {"current_node": current, "events": state.get("events", []) + [{"node_id": current, "status": "succeeded"}]}
        builder.add_node(node_id, advance)
    builder.set_entry_point("analyze_sources")
    for source, target in zip(NODES[:-1], NODES[1:]):
        builder.add_edge(source, target)
    builder.add_edge("finalize", END)
    return builder.compile()
