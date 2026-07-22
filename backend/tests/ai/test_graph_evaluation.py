from copy import deepcopy
from pathlib import Path

import pytest

from app.ai.evaluation import evaluate_bundle
from app.ai.generation import generate_lesson_bundle
from app.ai.graph import ModelReviewOutput, ReviewerIssue, build_langgraph, review_artifacts, review_quality, route_after_review
from app.ai.llm_client import LLMResult
from app.ai.schemas import LessonContext
from app.ai.vector_store import ProjectVectorStore


@pytest.fixture(scope="module")
def valid_artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp("graph-store")
    context = LessonContext(project_id="graph-project", subject="科学", grade="四年级", lesson_topic="水的蒸发")
    return generate_lesson_bundle(context, store=ProjectVectorStore(Path(root), force_json=True)).artifacts


def _scenario(artifacts, name):
    value = deepcopy(artifacts)
    attempts = {}
    cancelled = False
    if name == "objective_without_activity":
        for stage in value["lesson_plan"]["stages"]:
            stage["objective_ids"] = ["OBJ-2"]
    elif name == "objective_without_assessment":
        value["lesson_plan"]["assessments"] = []
        for exercise in value["exercise_set"]["exercises"]:
            exercise["objective_ids"] = ["OBJ-2"]
    elif name == "slide_count":
        value["slide_deck"]["slides"] = value["slide_deck"]["slides"][:10]
        value["speaker_notes"]["notes"] = value["speaker_notes"]["notes"][:10]
    elif name == "missing_note":
        value["speaker_notes"]["notes"].pop()
    elif name == "missing_level":
        value["exercise_set"]["exercises"] = [item for item in value["exercise_set"]["exercises"] if item["level"] != "提高"]
    elif name == "generated_unmarked":
        value["exercise_set"]["exercises"][0]["needs_teacher_review"] = False
    elif name == "duplicate_slide":
        value["slide_deck"]["slides"][1]["slide_id"] = value["slide_deck"]["slides"][0]["slide_id"]
    elif name == "repair_limit":
        value["speaker_notes"]["notes"].pop()
        attempts = {"generate_notes_exercises": 2}
    elif name == "cancelled":
        cancelled = True
    issues = review_artifacts(value)
    return {"artifacts": value, "issues": issues, "attempts": attempts, "cancelled": cancelled}


@pytest.mark.parametrize(
    ("name", "expected_route", "expected_issue"),
    [
        ("normal", "human_confirm", None),
        ("objective_without_activity", "design_lesson", "objective_without_activity"),
        ("objective_without_assessment", "design_lesson", "objective_unassessed"),
        ("slide_count", "generate_slides", "slide_count"),
        ("missing_note", "generate_notes_exercises", "missing_note"),
        ("missing_level", "generate_notes_exercises", "missing_exercise_level"),
        ("generated_unmarked", "generate_notes_exercises", "generated_exercise_unmarked"),
        ("duplicate_slide", "generate_slides", "duplicate_slide_id"),
        ("repair_limit", "human_confirm", "missing_note"),
        ("cancelled", "cancelled", None),
    ],
)
def test_ten_graph_quality_routes(valid_artifacts, name, expected_route, expected_issue):
    state = _scenario(valid_artifacts, name)
    issue_types = {item["issue_type"] for item in state["issues"]}
    if expected_issue:
        assert expected_issue in issue_types
    assert route_after_review(state) == expected_route


def test_compiled_langgraph_pauses_before_human_confirmation(valid_artifacts):
    graph = build_langgraph()
    assert graph is not None
    result = graph.invoke({"artifacts": valid_artifacts, "attempts": {}, "events": [], "trace_id": "graph-trace"})
    assert result["current_node"] == "review_quality"
    assert any(event["node_id"] == "review_quality" for event in result["events"])


def test_node_exception_is_bounded_and_sent_to_human(valid_artifacts):
    def fail(_state):
        raise RuntimeError("synthetic model failure")

    graph = build_langgraph({"design_lesson": fail})
    result = graph.invoke({"artifacts": valid_artifacts, "attempts": {}, "events": [], "trace_id": "error-trace"})
    assert result["failed"] is True
    assert result["error"] == "synthetic model failure"
    assert result["issues"][0]["issue_type"] == "node_exception"


def test_bundle_evaluation_is_machine_readable(valid_artifacts):
    report = evaluate_bundle(valid_artifacts)
    assert set(report) >= {"issue_count", "fail_count", "warn_count", "invalid_citation_count", "issues"}
    assert report["fail_count"] == 0


def test_structured_model_review_adds_but_cannot_remove_rule_issues(valid_artifacts):
    class Reviewer:
        configured = True

        @staticmethod
        def invoke_structured(system, user, output_model, trace_id=None):
            assert output_model is ModelReviewOutput
            output = ModelReviewOutput(issues=[ReviewerIssue(issue_type="age_language", target_id="SLIDE-01", severity="warn", suggestion="请教师确认语言是否适龄")])
            return output, LLMResult("{}", "fake-reviewer", 2, trace_id=trace_id or "review")

    issues = review_quality(valid_artifacts, llm=Reviewer(), trace_id="review-trace")
    assert any(item["issue_type"] == "age_language" and item["target_id"] == "SLIDE-01" for item in issues)
