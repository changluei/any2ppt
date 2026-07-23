from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from .exceptions import AIConfigurationError
from .llm_client import DeepSeekClient
from .schemas import (
    Activity,
    Assessment,
    Citation,
    Exercise,
    GenerationBundle,
    LessonBlueprint,
    LessonContext,
    Objective,
    SkillRequest,
    Slide,
    SkillResponse,
    SpeakerNote,
    TraceInfo,
)
from .skills import SlideOutline, run_skill
from .vector_store import ProjectVectorStore


class LocalRevisionOutput(BaseModel):
    changed_block: dict[str, Any]


def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
    unique: dict[tuple[str, str], Citation] = {}
    for citation in citations:
        unique[(citation.source_id, citation.chunk_id)] = citation
    return list(unique.values())


def _fallback_outlines(context: LessonContext) -> list[SlideOutline]:
    titles = [
        "课题与学习任务", "情境问题", "说说已有经验", "本课学习目标", "观察资料",
        "发现关键信息", "合作探究", "交流与质疑", "方法梳理", "例题示范",
        "基础练习", "巩固练习", "提高挑战", "易错提醒", "课堂小结", "自我评价",
    ]
    return [
        SlideOutline(
            title=title,
            teaching_stage=("STAGE-1" if index <= 4 else "STAGE-2" if index <= 10 else "STAGE-3" if index <= 14 else "STAGE-4"),
            objective_ids=["OBJ-1"] if index <= 8 else ["OBJ-2"] if index <= 14 else ["OBJ-1", "OBJ-2"],
            purpose=f"围绕“{context.lesson_topic}”形成可观察的学习证据",
        )
        for index, title in enumerate(titles, 1)
    ]


def _normalize_outlines(
    context: LessonContext,
    outlines: list[SlideOutline],
    objective_ids: set[str],
    stage_ids: set[str],
) -> list[SlideOutline]:
    normalized = list(outlines[:18])
    fallback = _fallback_outlines(context)
    while len(normalized) < 12:
        normalized.append(fallback[len(normalized)])
    safe: list[SlideOutline] = []
    default_ids = sorted(objective_ids)[:1]
    default_stage = sorted(stage_ids)[0]
    for outline in normalized:
        ids = [item for item in outline.objective_ids if item in objective_ids] or default_ids
        stage = outline.teaching_stage if outline.teaching_stage in stage_ids else default_stage
        safe.append(outline.model_copy(update={"objective_ids": ids, "teaching_stage": stage}))
    return safe


def _normalize_blueprint_links(
    objectives: list[Objective],
    activities: list[Activity],
    assessments: list[Assessment],
) -> tuple[list[Activity], list[Assessment], bool]:
    valid_ids = {item.id for item in objectives}
    first_id = objectives[0].id
    changed = False
    safe_activities: list[Activity] = []
    for item in activities:
        ids = [objective_id for objective_id in item.objective_ids if objective_id in valid_ids]
        if not ids:
            ids = [first_id]
        changed = changed or ids != item.objective_ids
        safe_activities.append(item.model_copy(update={"objective_ids": ids}))
    safe_assessments: list[Assessment] = []
    for item in assessments:
        ids = [objective_id for objective_id in item.objective_ids if objective_id in valid_ids]
        if not ids:
            ids = [first_id]
        changed = changed or ids != item.objective_ids
        safe_assessments.append(item.model_copy(update={"objective_ids": ids}))
    activity_coverage = {objective_id for item in safe_activities for objective_id in item.objective_ids}
    assessment_coverage = {objective_id for item in safe_assessments for objective_id in item.objective_ids}
    for objective in objectives:
        if objective.core and objective.id not in activity_coverage:
            first = safe_activities[0]
            safe_activities[0] = first.model_copy(update={"objective_ids": list(dict.fromkeys(first.objective_ids + [objective.id]))})
            changed = True
        if objective.core and objective.id not in assessment_coverage:
            first = safe_assessments[0]
            safe_assessments[0] = first.model_copy(update={"objective_ids": list(dict.fromkeys(first.objective_ids + [objective.id]))})
            changed = True
    return safe_activities, safe_assessments, changed


def _normalize_exercise_links(exercises: list[Exercise], objectives: list[Objective]) -> tuple[list[Exercise], bool]:
    valid_ids = {item.id for item in objectives}
    first_id = objectives[0].id
    changed = False
    safe: list[Exercise] = []
    for exercise in exercises:
        ids = [objective_id for objective_id in exercise.objective_ids if objective_id in valid_ids] or [first_id]
        changed = changed or ids != exercise.objective_ids
        safe.append(exercise.model_copy(update={"objective_ids": ids}))
    coverage = {objective_id for item in safe for objective_id in item.objective_ids}
    for objective in objectives:
        if objective.core and objective.id not in coverage:
            target = safe[-1]
            safe[-1] = target.model_copy(update={"objective_ids": list(dict.fromkeys(target.objective_ids + [objective.id]))})
            changed = True
    return safe, changed


def _allocate_note_minutes(slides: list[SlideOutline], activities: list[Activity]) -> list[int]:
    total = sum(activity.time_minutes for activity in activities)
    if not slides:
        return []
    base, remainder = divmod(total, len(slides))
    minutes = [base] * len(slides)
    for index in range(remainder):
        minutes[index] += 1
    return minutes


def _materialize_artifacts(
    context: LessonContext,
    blueprint: LessonBlueprint,
    outlines: list[SlideOutline],
    exercises: list[Exercise],
) -> dict[str, dict[str, Any]]:
    objective_ids = {item.id for item in blueprint.objectives}
    outlines = _normalize_outlines(context, outlines, objective_ids, {item.id for item in blueprint.activities})
    source_slides = set(range(5, min(9, len(outlines) + 1)))
    slides: list[Slide] = []
    for index, outline in enumerate(outlines, 1):
        citations = blueprint.citations[:2] if index in source_slides else []
        evidence_line = "\n\n> 资料依据可在来源面板查看" if citations else ""
        markdown = f"# {outline.title}\n\n{outline.purpose}\n\n**学习主题：** {context.lesson_topic}{evidence_line}"
        slides.append(
            Slide(
                slide_id=f"SLIDE-{index:02d}",
                order=index,
                title=outline.title,
                markdown=markdown,
                teaching_stage=outline.teaching_stage,
                objective_ids=outline.objective_ids,
                citations=citations,
            )
        )

    note_minutes = _allocate_note_minutes(outlines, blueprint.activities)
    notes = [
        SpeakerNote(
            slide_id=slide.slide_id,
            explanation=f"围绕“{slide.title}”进行简洁讲解，先让学生表达，再根据回答追问理由。",
            questions=[f"关于“{slide.title}”，你观察到了什么？依据是什么？"],
            expected_answers=["学生结合本页信息和已有经验说明发现与理由。"],
            transition="接下来把这一发现用于下一个学习任务。",
            board_notes=slide.title,
            estimated_minutes=note_minutes[index],
        )
        for index, slide in enumerate(slides)
    ]
    citation_dicts = [item.model_dump(mode="json") for item in blueprint.citations]
    artifacts = {
        "lesson_plan": {
            "title": blueprint.title,
            "grade": blueprint.grade,
            "subject": blueprint.subject,
            "objectives": [item.model_dump(mode="json") for item in blueprint.objectives],
            "key_points": blueprint.key_points,
            "difficult_points": blueprint.difficult_points,
            "stages": [item.model_dump(mode="json") for item in blueprint.activities],
            "assessments": [item.model_dump(mode="json") for item in blueprint.assessments],
            "teaching_strategies": blueprint.teaching_strategies,
            "citations": citation_dicts,
        },
        "slide_deck": {
            "deck_title": context.lesson_topic,
            "theme": "seriph",
            "slides": [item.model_dump(mode="json") for item in slides],
            "citations": citation_dicts,
        },
        "speaker_notes": {"notes": [item.model_dump(mode="json") for item in notes]},
        "exercise_set": {"exercises": [item.model_dump(mode="json") for item in exercises]},
    }
    return artifacts


def merge_blueprint_responses(
    blueprint: LessonBlueprint,
    responses: list[SkillResponse],
) -> LessonBlueprint:
    """Merge citations and warnings produced by later graph nodes."""
    merged = blueprint.model_copy(deep=True)
    merged.citations = _dedupe_citations(
        list(merged.citations) + [citation for response in responses for citation in response.citations]
    )
    merged.warnings = list(
        dict.fromkeys(
            list(merged.warnings) + [warning for response in responses for warning in response.warnings]
        )
    )
    return merged


def design_lesson_blueprint(
    context: LessonContext,
    *,
    llm=None,
    store: ProjectVectorStore | None = None,
    trace_id: str | None = None,
) -> tuple[LessonBlueprint, list[SkillResponse]]:
    """Run only the standard/objective/activity skills used by the design node."""
    vector_store = store or ProjectVectorStore()
    run_trace = trace_id or str(uuid.uuid4())
    standard = run_skill(
        "course_standard_interpretation",
        SkillRequest(context=context),
        llm=llm,
        store=vector_store,
        trace_id=run_trace,
    )
    objectives_response = run_skill(
        "learning_objectives",
        SkillRequest(context=context, parameters={"course_standard": standard.result}),
        llm=llm,
        store=vector_store,
        trace_id=run_trace,
    )
    activities_response = run_skill(
        "teaching_activities",
        SkillRequest(context=context, parameters={"objectives": objectives_response.result["objectives"]}),
        llm=llm,
        store=vector_store,
        trace_id=run_trace,
    )
    responses = [standard, objectives_response, activities_response]
    objectives = [Objective.model_validate(item) for item in objectives_response.result["objectives"]]
    activities = [Activity.model_validate(item) for item in activities_response.result["activities"]]
    assessments = [Assessment.model_validate(item) for item in activities_response.result["assessments"]]
    activities, assessments, links_changed = _normalize_blueprint_links(objectives, activities, assessments)
    warnings = list(dict.fromkeys(warning for response in responses for warning in response.warnings))
    if links_changed:
        warnings.append("已按教学目标自动修正活动与评价中的目标编号关联，请教师复核。")
    blueprint = LessonBlueprint(
        title=f"{context.lesson_topic} 教学设计",
        grade=context.grade,
        subject=context.subject,
        objectives=objectives,
        key_points=objectives_response.result["key_points"],
        difficult_points=objectives_response.result["difficult_points"],
        activities=activities,
        assessments=assessments,
        teaching_strategies=["问题驱动", "合作探究", "分层评价"],
        citations=_dedupe_citations([citation for response in responses for citation in response.citations]),
        warnings=warnings,
    )
    return blueprint, responses


def generate_slide_outlines(
    context: LessonContext,
    blueprint: LessonBlueprint,
    *,
    llm=None,
    store: ProjectVectorStore | None = None,
    trace_id: str | None = None,
) -> tuple[list[SlideOutline], SkillResponse]:
    """Run the slide skill without generating notes or exercises."""
    response = run_skill(
        "slide_narrative",
        SkillRequest(context=context, parameters={"blueprint": blueprint.model_dump(mode="json")}),
        llm=llm,
        store=store or ProjectVectorStore(),
        trace_id=trace_id or str(uuid.uuid4()),
    )
    return [SlideOutline.model_validate(item) for item in response.result["slides"]], response


def generate_exercises(
    context: LessonContext,
    blueprint: LessonBlueprint,
    *,
    llm=None,
    store: ProjectVectorStore | None = None,
    trace_id: str | None = None,
) -> tuple[list[Exercise], SkillResponse, bool]:
    """Run the exercise skill and normalize objective coverage."""
    response = run_skill(
        "exercise_assessment",
        SkillRequest(
            context=context,
            parameters={"objectives": [item.model_dump(mode="json") for item in blueprint.objectives]},
        ),
        llm=llm,
        store=store or ProjectVectorStore(),
        trace_id=trace_id or str(uuid.uuid4()),
    )
    exercises = [Exercise.model_validate(item) for item in response.result["exercises"]]
    exercises, links_changed = _normalize_exercise_links(exercises, blueprint.objectives)
    return exercises, response, links_changed


def materialize_lesson_artifacts(
    context: LessonContext,
    blueprint: LessonBlueprint,
    outlines: list[SlideOutline],
    exercises: list[Exercise],
) -> dict[str, dict[str, Any]]:
    """Public graph-node adapter for deriving the four aligned artifacts."""
    return _materialize_artifacts(context, blueprint, outlines, exercises)


def build_lesson_blueprint(
    context: LessonContext,
    *,
    llm=None,
    store: ProjectVectorStore | None = None,
    trace_id: str | None = None,
) -> tuple[LessonBlueprint, list[SlideOutline], list[Exercise], list, bool]:
    vector_store = store or ProjectVectorStore()
    run_trace = trace_id or str(uuid.uuid4())
    blueprint, responses = design_lesson_blueprint(
        context,
        llm=llm,
        store=vector_store,
        trace_id=run_trace,
    )
    outlines, slide_response = generate_slide_outlines(
        context,
        blueprint,
        llm=llm,
        store=vector_store,
        trace_id=run_trace,
    )
    exercises, exercise_response, exercise_links_changed = generate_exercises(
        context,
        blueprint,
        llm=llm,
        store=vector_store,
        trace_id=run_trace,
    )
    responses.extend([slide_response, exercise_response])
    blueprint = merge_blueprint_responses(blueprint, [slide_response, exercise_response])
    if exercise_links_changed:
        blueprint.warnings.append("已按教学目标自动修正练习中的目标编号关联，请教师复核。")
    return blueprint, outlines, exercises, responses, any(response.degraded for response in responses)


def generate_lesson_bundle(
    context: LessonContext,
    *,
    llm=None,
    store: ProjectVectorStore | None = None,
    trace_id: str | None = None,
) -> GenerationBundle:
    started = time.perf_counter()
    run_trace = trace_id or str(uuid.uuid4())
    blueprint, outlines, exercises, responses, degraded = build_lesson_blueprint(
        context,
        llm=llm,
        store=store,
        trace_id=run_trace,
    )
    artifacts = _materialize_artifacts(context, blueprint, outlines, exercises)
    warnings = list(blueprint.warnings)
    if degraded:
        warnings.append("当前产物包含规则降级内容，不代表 DeepSeek 生成成功，必须由教师确认。")
    warnings = list(dict.fromkeys(warnings))
    models = [response.trace.model for response in responses if response.trace.model != "rule-based-fallback"]
    model = models[0] if models else "rule-based-fallback"
    trace = TraceInfo(
        trace_id=run_trace,
        model=model,
        model_status="degraded" if degraded else "succeeded",
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        retrieval_count=sum(response.trace.retrieval_count for response in responses),
        attempts=sum(response.trace.attempts for response in responses),
        usage=None,
    )
    return GenerationBundle(
        artifacts=artifacts,
        citations=blueprint.citations,
        warnings=warnings,
        model=model,
        degraded=degraded,
        trace=trace,
    )


def _rule_revision(block: dict[str, Any], target_type: str, instruction: str) -> dict[str, Any]:
    revised = deepcopy(block)
    clean_instruction = instruction.strip()
    if target_type == "slide":
        markdown = revised.get("markdown", "")
        if any(word in clean_instruction for word in ("精简", "简洁", "减少文字")):
            lines = [line for line in markdown.splitlines() if line.strip()]
            revised["markdown"] = "\n\n".join(lines[:3])
        else:
            revised["markdown"] = f"{markdown}\n\n> 教师调整要求：{clean_instruction}".strip()
    elif target_type == "note":
        revised["explanation"] = f"{revised.get('explanation', '')}\n教师调整：{clean_instruction}".strip()
    elif target_type == "exercise":
        if any(word in clean_instruction for word in ("简单", "降低难度", "容易")):
            revised["difficulty"] = max(1, int(revised.get("difficulty", 2)) - 1)
        if any(word in clean_instruction for word in ("困难", "提高难度", "挑战")):
            revised["difficulty"] = min(5, int(revised.get("difficulty", 2)) + 1)
        revised["question"] = f"{revised.get('question', '')}\n（教师要求：{clean_instruction}）".strip()
        revised["needs_teacher_review"] = True
    else:
        revised["teacher_revision"] = clean_instruction
    revised["revision_mode"] = "rule-based-fallback"
    return revised


def revise_block(
    content: dict,
    target_type: str,
    target_id: str,
    instruction: str,
    *,
    llm=None,
    citations: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    updated = json.loads(json.dumps(content, ensure_ascii=False))
    collections = {"slide": "slides", "note": "notes", "exercise": "exercises"}
    key = collections.get(target_type, target_type)
    rows = updated.get(key, [])
    id_fields = {"slides": "slide_id", "notes": "slide_id", "exercises": "exercise_id"}
    id_field = id_fields.get(key, "id")
    for index, row in enumerate(rows):
        if row.get(id_field) != target_id:
            continue
        client = llm or DeepSeekClient()
        try:
            if getattr(client, "configured", True) is False:
                raise AIConfigurationError("模型未配置")
            prompt = (
                f"目标类型：{target_type}\n目标块：{json.dumps(row, ensure_ascii=False)}"
                f"\n教师指令：{instruction}\n可用引用：{json.dumps(citations or [], ensure_ascii=False)}"
                "\n只返回 changed_block，不得改动稳定 ID，不得重写其他块；事实变化只能使用给定引用。"
            )
            output, _ = client.invoke_structured(
                "你是局部教学内容修改器。只输出 JSON。",
                prompt,
                LocalRevisionOutput,
            )
            changed = output.changed_block
            changed[id_field] = target_id
        except AIConfigurationError:
            changed = _rule_revision(row, target_type, instruction)
        rows[index] = changed
        return updated, [target_id]
    raise ValueError("未找到要修改的目标内容")
