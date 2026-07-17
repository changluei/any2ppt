import json
from .llm_client import DeepSeekClient
from .schemas import Citation, GenerationBundle, LessonContext
from .vector_store import ProjectVectorStore
from .exceptions import AIConfigurationError


def _citations(rows: list[dict]) -> list[Citation]:
    return [Citation(source_id=r["source_id"], chunk_id=r["chunk_id"], filename=r["filename"], location=r["location"], quote=r["content"][:220]) for r in rows]


def _rule_based_bundle(context: LessonContext, citations: list[Citation]) -> GenerationBundle:
    """透明的规则降级草案：由输入动态构造，不冒充模型结果。"""
    topic, grade = context.lesson_topic, context.grade
    objectives = [
        {"id": "OBJ-1", "behavior": f"能用自己的语言说明“{topic}”的核心概念", "condition": "在阅读资料和课堂讨论后", "criterion": "表达包含至少两个关键信息"},
        {"id": "OBJ-2", "behavior": f"能运用“{topic}”相关知识完成基础任务", "condition": "在例题或情境任务中", "criterion": "正确率达到 80%"},
    ]
    stages = [
        {"id": "STAGE-1", "name": "情境导入", "time_minutes": 5, "teacher_actions": "用贴近生活的问题引出课题", "student_actions": "观察、猜想并说出已有经验", "objective_ids": ["OBJ-1"], "assessment": "口头诊断"},
        {"id": "STAGE-2", "name": "探究新知", "time_minutes": 20, "teacher_actions": "呈现证据并组织合作探究", "student_actions": "阅读、讨论、归纳", "objective_ids": ["OBJ-1", "OBJ-2"], "assessment": "过程观察与追问"},
        {"id": "STAGE-3", "name": "分层练习", "time_minutes": 12, "teacher_actions": "提供由易到难的任务并反馈", "student_actions": "独立完成后互相说明思路", "objective_ids": ["OBJ-2"], "assessment": "练习正确率"},
        {"id": "STAGE-4", "name": "总结迁移", "time_minutes": 3, "teacher_actions": "引导提炼方法并布置迁移问题", "student_actions": "总结收获并自评", "objective_ids": ["OBJ-1", "OBJ-2"], "assessment": "出口条"},
    ]
    slides = []
    slide_titles = ["课题与学习任务", "生活中的问题", "我们已经知道什么", "本课学习目标", "资料观察", "关键概念", "合作探究", "方法梳理", "例题示范", "基础练习", "巩固练习", "提高挑战", "易错提醒", "课堂小结", "自我评价"]
    for i, title in enumerate(slide_titles, 1):
        stage = stages[min((i - 1) // 4, 3)]
        slides.append({"slide_id": f"SLIDE-{i:02d}", "order": i, "title": title, "layout": "default", "markdown": f"# {title}\n\n{topic} · {grade}\n\n> 请结合课堂互动补充内容", "teaching_stage": stage["id"], "objective_ids": stage["objective_ids"], "citations": [c.model_dump() for c in citations[:1]] if 5 <= i <= 8 else []})
    notes = [{"slide_id": s["slide_id"], "explanation": f"围绕“{s['title']}”组织简洁讲解，并根据学生反馈追问。", "questions": [f"你从这一页发现了什么？为什么？"], "expected_answers": ["学生结合观察说出理由"], "transition": "接下来我们把发现用于新的任务。", "board_notes": s["title"], "estimated_minutes": 3} for s in slides]
    exercises = [
        {"exercise_id": "EX-1", "level": "基础", "objective_ids": ["OBJ-1"], "question": f"用一句话说明“{topic}”的核心意思。", "type": "简答", "difficulty": 1, "answer": "依据课堂归纳作答。", "explanation": "检查核心概念是否准确。", "source": "generated", "needs_teacher_review": True},
        {"exercise_id": "EX-2", "level": "巩固", "objective_ids": ["OBJ-2"], "question": f"选择一个课堂情境，运用“{topic}”相关方法完成任务。", "type": "应用", "difficulty": 2, "answer": "答案随具体情境确定。", "explanation": "关注方法应用过程。", "source": "generated", "needs_teacher_review": True},
        {"exercise_id": "EX-3", "level": "提高", "objective_ids": ["OBJ-1", "OBJ-2"], "question": f"比较两种解决“{topic}”问题的方法并说明选择。", "type": "开放题", "difficulty": 3, "answer": "观点合理且证据充分即可。", "explanation": "评价迁移与论证能力。", "source": "generated", "needs_teacher_review": True},
    ]
    common = {"citations": [c.model_dump() for c in citations]}
    artifacts = {
        "lesson_plan": {"title": f"{topic} 教学设计", "grade": grade, "objectives": objectives, "key_points": [f"理解并应用{topic}的核心知识"], "difficult_points": ["把概念迁移到新情境"], "stages": stages, **common},
        "slide_deck": {"deck_title": topic, "theme": "seriph", "slides": slides, **common},
        "speaker_notes": {"notes": notes},
        "exercise_set": {"exercises": exercises},
    }
    warning = "未配置或无法调用 DeepSeek；当前为规则生成的降级草案，必须由教师确认，不代表模型生成成功。"
    if not citations:
        warning += " 当前没有可追溯资料，通用建议未附引用。"
    return GenerationBundle(artifacts=artifacts, citations=citations, warnings=[warning], model="rule-based-fallback", degraded=True)


def generate_lesson_bundle(context: LessonContext) -> GenerationBundle:
    rows = ProjectVectorStore().similarity_search(context.project_id, f"{context.lesson_topic} 课程标准 教学目标 重点", 8, context.selected_source_ids or None)
    citations = _citations(rows)
    evidence = "\n".join(f"[{i + 1}] {c.filename} {c.location}: {c.quote}" for i, c in enumerate(citations)) or "无可用资料"
    system = "你是小学教师备课助手。只输出 JSON；引用只能使用给出的证据。目标、活动、评价编号必须对应。课件 12-18 页。原创练习标记 source=generated 和 needs_teacher_review=true。"
    prompt = f"课程上下文：{context.model_dump_json()}\n证据：{evidence}\n输出 artifacts（lesson_plan/slide_deck/speaker_notes/exercise_set）、warnings。"
    try:
        data, result = DeepSeekClient().invoke_json(system, prompt)
        return GenerationBundle(artifacts=data["artifacts"], citations=citations, warnings=data.get("warnings", []), model=result.model)
    except AIConfigurationError:
        return _rule_based_bundle(context, citations)


def revise_block(content: dict, target_type: str, target_id: str, instruction: str) -> tuple[dict, list[str]]:
    updated = json.loads(json.dumps(content, ensure_ascii=False))
    collections = {"slide": "slides", "note": "notes", "exercise": "exercises"}
    key = collections.get(target_type, target_type)
    rows = updated.get(key, [])
    id_fields = {"slides": "slide_id", "notes": "slide_id", "exercises": "exercise_id"}
    id_field = id_fields.get(key, "id")
    for row in rows:
        if row.get(id_field) == target_id:
            row["teacher_revision"] = instruction
            return updated, [target_id]
    raise ValueError("未找到要修改的目标内容")

