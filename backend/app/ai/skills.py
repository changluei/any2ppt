from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from .exceptions import AIConfigurationError
from .llm_client import DeepSeekClient
from .retriever import EvidenceSet, retrieve_evidence
from .schemas import (
    Activity,
    Assessment,
    Exercise,
    LessonContext,
    Objective,
    SkillRequest,
    SkillResponse,
    TraceInfo,
)
from .vector_store import ProjectVectorStore


class CourseStandardOutput(BaseModel):
    requirements: list[str] = Field(min_length=1)
    key_concepts: list[str] = Field(default_factory=list)
    evidence_summary: str
    general_suggestions: list[str] = Field(default_factory=list)


class LearningObjectivesOutput(BaseModel):
    objectives: list[Objective] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    difficult_points: list[str] = Field(min_length=1)


class TeachingActivitiesOutput(BaseModel):
    activities: list[Activity] = Field(min_length=1)
    assessments: list[Assessment] = Field(min_length=1)


class SlideOutline(BaseModel):
    title: str
    teaching_stage: str
    objective_ids: list[str] = Field(default_factory=list)
    purpose: str
    layout: str = "default"
    visual_intent: str = ""


class SlideNarrativeOutput(BaseModel):
    slides: list[SlideOutline] = Field(min_length=1, max_length=18)


class ExerciseAssessmentOutput(BaseModel):
    exercises: list[Exercise] = Field(min_length=3)


@dataclass(frozen=True)
class SkillInfo:
    id: str
    name: str
    description: str
    required_inputs: tuple[str, ...]


class TeachingSkill:
    info: ClassVar[SkillInfo]
    output_model: ClassVar[type[BaseModel]]
    query_template: ClassVar[str]
    instructions: ClassVar[str]

    def evidence_query(self, context: LessonContext) -> str:
        return self.query_template.format(
            topic=context.lesson_topic,
            subject=context.subject,
            grade=context.grade,
        )

    def fallback(self, request: SkillRequest, evidence: EvidenceSet) -> BaseModel:
        raise NotImplementedError

    def run(
        self,
        request: SkillRequest,
        *,
        llm=None,
        store: ProjectVectorStore | None = None,
        trace_id: str | None = None,
    ) -> SkillResponse:
        run_trace = trace_id or str(uuid.uuid4())
        started = time.perf_counter()
        evidence = retrieve_evidence(request.context, self.evidence_query(request.context), store=store)
        client = llm or DeepSeekClient()
        warnings = list(evidence.warnings)
        degraded = False
        attempts = 0
        model_name = "rule-based-fallback"
        usage = None

        evidence_text = "\n".join(
            f"[{index}] {row['filename']} {row['location']}：{row['content']}"
            for index, row in enumerate(evidence.rows, 1)
        ) or "无可用证据"
        system = (
            "你是小学教学设计助手。只输出符合 JSON Schema 的对象。"
            "证据不足时只能给通用建议，禁止编造课标原文、页码、来源或学生数据。"
            "所有建议须适合指定年级，并保留教师最终确认。"
        )
        user = (
            f"Skill：{self.info.id}\n任务要求：{self.instructions}"
            f"\n课程上下文：{request.context.model_dump_json()}"
            f"\n教师指令：{request.instruction or '无'}"
            f"\n参数：{request.parameters}"
            f"\n检索证据：\n{evidence_text}"
        )
        try:
            if getattr(client, "configured", True) is False:
                raise AIConfigurationError("模型未配置")
            output, result = client.invoke_structured(system, user, self.output_model, trace_id=run_trace)
            model_name = result.model
            attempts = result.attempts
            usage = result.usage
        except AIConfigurationError:
            output = self.fallback(request, evidence)
            degraded = True
            warnings.append("未配置 DeepSeek；当前 Skill 返回规则降级草案，必须由教师确认。")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        trace = TraceInfo(
            trace_id=run_trace,
            skill_id=self.info.id,
            model=model_name,
            model_status="degraded" if degraded else "succeeded",
            elapsed_ms=elapsed_ms,
            retrieval_count=len(evidence.rows),
            attempts=attempts,
            usage=usage,
        )
        return SkillResponse(
            skill_id=self.info.id,
            result=output.model_dump(mode="json"),
            citations=evidence.citations,
            warnings=list(dict.fromkeys(warnings)),
            trace=trace,
            degraded=degraded,
        )


class CourseStandardSkill(TeachingSkill):
    info = SkillInfo(
        "course_standard_interpretation",
        "课程标准解读",
        "从课标与教材资料中提炼本课要求和可追溯依据",
        ("lesson_topic", "subject", "grade"),
    )
    output_model = CourseStandardOutput
    query_template = "{grade}{subject} {topic} 课程标准 学段要求 核心素养"
    instructions = "提炼与本课直接相关的要求、核心概念和证据摘要。"

    def fallback(self, request: SkillRequest, evidence: EvidenceSet) -> BaseModel:
        requirements = [row["content"][:180] for row in evidence.rows[:3]]
        if not requirements:
            requirements = [f"围绕“{request.context.lesson_topic}”建立适龄的知识理解与应用任务"]
        return CourseStandardOutput(
            requirements=requirements,
            key_concepts=[request.context.lesson_topic],
            evidence_summary="依据已检索资料整理" if evidence.rows else "无课标证据，当前仅为通用框架",
            general_suggestions=["教师需对照本地课程标准原文确认具体表述"],
        )


class LearningObjectivesSkill(TeachingSkill):
    info = SkillInfo(
        "learning_objectives",
        "学情与教学目标设计",
        "设计可观察、可评价且符合小学年龄特点的目标",
        ("grade", "student_profile", "lesson_topic"),
    )
    output_model = LearningObjectivesOutput
    query_template = "{grade}{subject} {topic} 教学目标 重点 难点 学情"
    instructions = "目标必须包含可观察行为、条件和评价标准，不使用了解、掌握等模糊词。"

    def fallback(self, request: SkillRequest, evidence: EvidenceSet) -> BaseModel:
        topic = request.context.lesson_topic
        return LearningObjectivesOutput(
            objectives=[
                Objective(id="OBJ-1", behavior=f"能用自己的语言说明“{topic}”的核心信息", condition="阅读资料并参与讨论后", criterion="至少说出两个关键信息"),
                Objective(id="OBJ-2", behavior=f"能在新情境中运用“{topic}”相关方法", condition="完成课堂任务时", criterion="主要步骤正确且能说明理由"),
            ],
            key_points=[f"理解“{topic}”的核心知识"],
            difficult_points=["把课堂所学迁移到新的问题情境"],
        )


class TeachingActivitiesSkill(TeachingSkill):
    info = SkillInfo(
        "teaching_activities",
        "教学活动与课堂流程设计",
        "建立目标—活动—评价一致的课堂流程",
        ("lesson_count", "lesson_topic"),
    )
    output_model = TeachingActivitiesOutput
    query_template = "{grade}{subject} {topic} 课堂活动 教学流程 评价"
    instructions = "设计单课时流程，给出时间、师生活动、目标编号和评价方式。"

    def fallback(self, request: SkillRequest, evidence: EvidenceSet) -> BaseModel:
        activities = [
            Activity(id="STAGE-1", name="情境导入", time_minutes=5, teacher_actions="用真实问题引出课题并诊断已有经验", student_actions="观察、猜想并表达已有认识", objective_ids=["OBJ-1"], assessment="口头诊断"),
            Activity(id="STAGE-2", name="探究新知", time_minutes=20, teacher_actions="呈现资料并组织观察、讨论和归纳", student_actions="阅读证据、合作讨论并形成解释", objective_ids=["OBJ-1", "OBJ-2"], assessment="观察记录与追问"),
            Activity(id="STAGE-3", name="分层练习", time_minutes=12, teacher_actions="提供由易到难的任务并进行反馈", student_actions="独立完成、同伴互评并说明方法", objective_ids=["OBJ-2"], assessment="练习正确率与方法说明"),
            Activity(id="STAGE-4", name="总结迁移", time_minutes=3, teacher_actions="引导总结并提出迁移问题", student_actions="归纳收获并进行自我评价", objective_ids=["OBJ-1", "OBJ-2"], assessment="出口条"),
        ]
        assessments = [
            Assessment(id="ASM-1", method="口头解释与课堂观察", objective_ids=["OBJ-1"], success_criteria="能够准确说出两个关键信息"),
            Assessment(id="ASM-2", method="分层练习与迁移任务", objective_ids=["OBJ-2"], success_criteria="主要步骤正确并能够说明理由"),
        ]
        return TeachingActivitiesOutput(activities=activities, assessments=assessments)


class SlideNarrativeSkill(TeachingSkill):
    info = SkillInfo(
        "slide_narrative",
        "课件叙事与页面规划",
        "规划适合课堂投影的课件叙事和逐页用途",
        ("lesson_topic", "grade"),
    )
    output_model = SlideNarrativeOutput
    query_template = "{grade}{subject} {topic} 教学材料 课堂呈现 例题"
    instructions = (
        "规划 12—18 页，每页聚焦一个教学目的，避免大段文字。"
        "必须结合课程上下文中的 theme_layouts、theme_guidance 和 theme_image_strategy 选择版式；"
        "layout 只能使用 theme_layouts 中的值，并通过 visual_intent 说明该页的视觉重点。"
    )

    def fallback(self, request: SkillRequest, evidence: EvidenceSet) -> BaseModel:
        titles = [
            "课题与学习任务", "情境问题", "说说已有经验", "本课学习目标", "观察资料",
            "发现关键信息", "合作探究", "交流与质疑", "方法梳理", "例题示范",
            "基础练习", "巩固练习", "提高挑战", "易错提醒", "课堂小结", "自我评价",
        ]
        layouts = request.context.theme_layouts or ["default"]
        slides = [
            SlideOutline(
                title=title,
                teaching_stage=("STAGE-1" if index <= 4 else "STAGE-2" if index <= 10 else "STAGE-3" if index <= 14 else "STAGE-4"),
                objective_ids=["OBJ-1"] if index <= 8 else ["OBJ-2"] if index <= 14 else ["OBJ-1", "OBJ-2"],
                purpose="引导学生观察、表达、应用并形成可评价的学习证据",
                layout=(
                    "cover" if index == 1 and "cover" in layouts
                    else "section" if index in {5, 11, 15} and "section" in layouts
                    else "fact" if index in {9, 14} and "fact" in layouts
                    else "quote" if index == 8 and "quote" in layouts
                    else "default" if "default" in layouts
                    else layouts[0]
                ),
                visual_intent="突出本页核心任务，控制文字数量并形成清晰视觉层级",
            )
            for index, title in enumerate(titles, 1)
        ]
        return SlideNarrativeOutput(slides=slides)


class ExerciseAssessmentSkill(TeachingSkill):
    info = SkillInfo(
        "exercise_assessment",
        "练习与评价设计",
        "生成基础、巩固、提高三个层次的练习与评价",
        ("grade", "lesson_topic"),
    )
    output_model = ExerciseAssessmentOutput
    query_template = "{grade}{subject} {topic} 练习 评价 易错点 应用"
    instructions = "至少生成基础、巩固、提高各一题；原创题必须标记 generated 和需教师确认。"

    def fallback(self, request: SkillRequest, evidence: EvidenceSet) -> BaseModel:
        topic = request.context.lesson_topic
        exercises = [
            Exercise(exercise_id="EX-1", level="基础", objective_ids=["OBJ-1"], question=f"用自己的话说明“{topic}”的核心信息。", type="简答", difficulty=1, answer="依据课堂归纳作答。", explanation="检查核心概念表达是否准确。", source="generated", needs_teacher_review=True),
            Exercise(exercise_id="EX-2", level="巩固", objective_ids=["OBJ-2"], question=f"在一个新的生活情境中运用“{topic}”相关方法解决问题。", type="应用", difficulty=2, answer="答案随教师确认的具体情境确定。", explanation="关注方法选择和主要步骤。", source="generated", needs_teacher_review=True),
            Exercise(exercise_id="EX-3", level="提高", objective_ids=["OBJ-1", "OBJ-2"], question=f"比较两种解决“{topic}”问题的方法，并说明你的选择。", type="开放题", difficulty=3, answer="观点合理、步骤清楚且证据充分即可。", explanation="评价迁移、比较和论证能力。", source="generated", needs_teacher_review=True),
        ]
        return ExerciseAssessmentOutput(exercises=exercises)


SKILL_CLASSES = [
    CourseStandardSkill,
    LearningObjectivesSkill,
    TeachingActivitiesSkill,
    SlideNarrativeSkill,
    ExerciseAssessmentSkill,
]
SKILLS = [skill.info for skill in SKILL_CLASSES]
_INSTANCES = {skill.info.id: skill() for skill in SKILL_CLASSES}


def registry() -> list[dict[str, Any]]:
    return [
        {
            "id": item.info.id,
            "name": item.info.name,
            "description": item.info.description,
            "required_inputs": list(item.info.required_inputs),
            "input_schema": SkillRequest.model_json_schema(),
            "output_schema": item.output_model.model_json_schema(),
        }
        for item in SKILL_CLASSES
    ]


def get_skill(skill_id: str) -> TeachingSkill:
    try:
        return _INSTANCES[skill_id]
    except KeyError as exc:
        raise ValueError(f"未知 Skill：{skill_id}") from exc


def run_skill(skill_id: str, request: SkillRequest, **kwargs) -> SkillResponse:
    return get_skill(skill_id).run(request, **kwargs)


_INTENT_RULES = {
    "course_standard_interpretation": {"课标": 4, "课程标准": 5, "核心素养": 3, "依据": 1},
    "learning_objectives": {"教学目标": 5, "目标": 3, "学情": 4, "重难点": 4},
    "teaching_activities": {"课堂活动": 5, "活动": 3, "流程": 3, "环节": 3},
    "slide_narrative": {"课件": 5, "幻灯片": 5, "讲稿": 4, "页面": 2},
    "exercise_assessment": {"练习": 5, "习题": 5, "评价": 3, "测验": 4},
}


def route_intent(text: str, explicit_task_type: str | None = None) -> str | None:
    if explicit_task_type is not None:
        return explicit_task_type if explicit_task_type in _INSTANCES else None
    scores = {
        skill_id: sum(weight for keyword, weight in rules.items() if keyword in text)
        for skill_id, rules in _INTENT_RULES.items()
    }
    best = max(scores.values(), default=0)
    winners = [skill_id for skill_id, score in scores.items() if score == best and score > 0]
    if len(winners) != 1 or best < 3:
        return None
    return winners[0]
