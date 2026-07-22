from pathlib import Path

import pytest

from app.ai.cache import GenerationCache, build_cache_key
from app.ai.evaluation import evaluate_router
from app.ai.generation import generate_lesson_bundle, revise_block
from app.ai.graph import review_artifacts
from app.ai.ingestion import Chunk
from app.ai.llm_client import LLMResult, _extract_json
from app.ai.schemas import LessonContext, SkillRequest
from app.ai.skills import CourseStandardOutput, registry, route_intent, run_skill
from app.ai.vector_store import ProjectVectorStore


@pytest.fixture
def context():
    return LessonContext(project_id="project-1", subject="科学", grade="四年级", lesson_topic="水的蒸发")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("请解读这节课对应的课程标准", "course_standard_interpretation"),
        ("帮我分析课标依据", "course_standard_interpretation"),
        ("设计可评价的教学目标", "learning_objectives"),
        ("结合学情调整重难点", "learning_objectives"),
        ("设计课堂活动", "teaching_activities"),
        ("安排教学流程和环节", "teaching_activities"),
        ("规划课件和逐页讲稿", "slide_narrative"),
        ("生成幻灯片页面", "slide_narrative"),
        ("设计分层练习", "exercise_assessment"),
        ("帮我看看", None),
    ],
)
def test_ten_router_cases(text, expected):
    assert route_intent(text) == expected


def test_explicit_route_has_priority_and_unknown_is_rejected():
    assert route_intent("生成课件", explicit_task_type="learning_objectives") == "learning_objectives"
    assert route_intent("生成课件", explicit_task_type="unknown") is None


def test_registry_exposes_five_independent_schemas():
    items = registry()
    assert len(items) == 5
    assert all(item["input_schema"] and item["output_schema"] for item in items)


class FakeCourseStandardLLM:
    configured = True

    @staticmethod
    def invoke_structured(system, user, output_model, trace_id=None):
        assert output_model is CourseStandardOutput
        output = CourseStandardOutput(
            requirements=["观察水量变化并依据证据解释蒸发现象"],
            key_concepts=["蒸发"],
            evidence_summary="依据给定资料",
        )
        return output, LLMResult("{}", "fake-model", 3, attempts=1, trace_id=trace_id or "trace")


def test_skill_uses_structured_model_and_real_retrieval_citation(tmp_path: Path, context):
    store = ProjectVectorStore(tmp_path, force_json=True)
    store.add_documents(context.project_id, "source-1", "教材.md", [Chunk("chunk-1", "水受热会加快蒸发。", "第 2 页", "hash-1")])
    response = run_skill(
        "course_standard_interpretation",
        SkillRequest(context=context),
        llm=FakeCourseStandardLLM(),
        store=store,
        trace_id="trace-1",
    )
    assert not response.degraded
    assert response.trace.model == "fake-model"
    assert response.citations[0].source_id == "source-1"
    assert response.citations[0].location == "第 2 页"


@pytest.mark.parametrize(
    "skill_id",
    [
        "course_standard_interpretation",
        "learning_objectives",
        "teaching_activities",
        "slide_narrative",
        "exercise_assessment",
    ],
)
def test_each_skill_has_honest_no_key_fallback(skill_id, tmp_path: Path, context):
    response = run_skill(skill_id, SkillRequest(context=context), store=ProjectVectorStore(tmp_path, force_json=True))
    assert response.degraded
    assert response.result
    assert response.trace.model_status == "degraded"
    assert any("未配置 DeepSeek" in warning for warning in response.warnings)


def test_full_bundle_comes_from_one_blueprint_and_is_aligned(tmp_path: Path, context):
    store = ProjectVectorStore(tmp_path, force_json=True)
    store.add_documents(context.project_id, "source-1", "课标.md", [Chunk("chunk-1", "科学课应让学生收集证据并形成解释。水受热会加快蒸发。", "第 3 页", "hash-1")])
    bundle = generate_lesson_bundle(context, store=store, trace_id="trace-bundle")
    slides = bundle.artifacts["slide_deck"]["slides"]
    notes = bundle.artifacts["speaker_notes"]["notes"]
    exercises = bundle.artifacts["exercise_set"]["exercises"]
    assert 12 <= len(slides) <= 18
    assert {item["slide_id"] for item in slides} == {item["slide_id"] for item in notes}
    assert {item["level"] for item in exercises} == {"基础", "巩固", "提高"}
    assert bundle.citations and bundle.citations[0].source_id == "source-1"
    assert bundle.trace.trace_id == "trace-bundle"
    assert not [issue for issue in review_artifacts(bundle.artifacts) if issue["severity"] == "fail"]


def test_local_revision_changes_only_target_slide(tmp_path: Path, context):
    bundle = generate_lesson_bundle(context, store=ProjectVectorStore(tmp_path, force_json=True))
    original = bundle.artifacts["slide_deck"]
    updated, changed_ids = revise_block(original, "slide", "SLIDE-02", "请精简页面文字")
    assert changed_ids == ["SLIDE-02"]
    assert updated["slides"][0] == original["slides"][0]
    assert updated["slides"][1] != original["slides"][1]
    assert updated["slides"][2:] == original["slides"][2:]


def test_exercise_revision_changes_difficulty_and_marks_review(tmp_path: Path, context):
    bundle = generate_lesson_bundle(context, store=ProjectVectorStore(tmp_path, force_json=True))
    original = bundle.artifacts["exercise_set"]
    updated, _ = revise_block(original, "exercise", "EX-2", "降低难度，表达更简单")
    target = next(item for item in updated["exercises"] if item["exercise_id"] == "EX-2")
    assert target["difficulty"] == 1
    assert target["needs_teacher_review"] is True


def test_json_extraction_accepts_fence_and_rejects_array():
    assert _extract_json("```json\n{\"ok\": true}\n```") == {"ok": True}
    with pytest.raises(Exception):
        _extract_json("[]")


def test_cache_key_is_namespaced_and_cache_hit_is_labeled():
    base = dict(input_version="v1", model="deepseek-chat", prompt_version="member4-v1", payload={"topic": "蒸发"})
    key_a = build_cache_key(project_id="project-a", **base)
    key_b = build_cache_key(project_id="project-b", **base)
    assert key_a != key_b
    cache = GenerationCache()
    cache.put(key_a, {"result": "A"})
    hit = cache.get(key_a)
    assert hit and hit.cached and hit.value == {"result": "A"}


def test_router_evaluation_is_machine_readable():
    report = evaluate_router([("设计课堂活动", "teaching_activities"), ("不确定", None)])
    assert report["accuracy"] == 1.0
    assert report["total"] == 2
