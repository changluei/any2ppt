from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Citation(BaseModel):
    source_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    location: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=600)
    score: float | None = Field(default=None, ge=0, le=1)


class RetrievalHit(Citation):
    content: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    content_hash: str = ""


class LessonContext(BaseModel):
    project_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    textbook_version: str = ""
    lesson_topic: str = Field(min_length=1)
    lesson_count: int = Field(default=1, ge=1, le=8)
    student_profile: str = ""
    selected_source_ids: list[str] = Field(default_factory=list)
    teacher_requirements: str = ""
    theme_id: str = "default"
    theme_name: str = ""
    theme_description: str = ""
    theme_layouts: list[str] = Field(default_factory=lambda: ["default"])
    theme_guidance: str = ""
    theme_image_strategy: str = ""


class TraceInfo(BaseModel):
    trace_id: str
    skill_id: str | None = None
    model: str
    model_status: Literal["succeeded", "degraded", "failed", "skipped"]
    elapsed_ms: int = Field(default=0, ge=0)
    retrieval_count: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    usage: dict[str, Any] | None = None


class Objective(BaseModel):
    id: str
    behavior: str
    condition: str
    criterion: str
    core: bool = True


class Activity(BaseModel):
    id: str
    name: str
    time_minutes: int = Field(ge=1, le=120)
    teacher_actions: str
    student_actions: str
    objective_ids: list[str] = Field(min_length=1)
    assessment: str


class Assessment(BaseModel):
    id: str
    method: str
    objective_ids: list[str] = Field(min_length=1)
    success_criteria: str


class LessonBlueprint(BaseModel):
    title: str
    grade: str
    subject: str
    objectives: list[Objective] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    difficult_points: list[str] = Field(min_length=1)
    activities: list[Activity] = Field(min_length=1)
    assessments: list[Assessment] = Field(min_length=1)
    teaching_strategies: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_alignment(self):
        objective_ids = {item.id for item in self.objectives}
        if not objective_ids:
            raise ValueError("教学蓝图至少需要一个教学目标")
        activity_ids = {oid for item in self.activities for oid in item.objective_ids}
        assessment_ids = {oid for item in self.assessments for oid in item.objective_ids}
        unknown = (activity_ids | assessment_ids) - objective_ids
        if unknown:
            raise ValueError(f"活动或评价引用了未知目标：{sorted(unknown)}")
        core_ids = {item.id for item in self.objectives if item.core}
        missing_activity = core_ids - activity_ids
        missing_assessment = core_ids - assessment_ids
        if missing_activity:
            raise ValueError(f"核心目标缺少活动：{sorted(missing_activity)}")
        if missing_assessment:
            raise ValueError(f"核心目标缺少评价：{sorted(missing_assessment)}")
        return self


class Slide(BaseModel):
    slide_id: str
    order: int = Field(ge=1)
    title: str
    layout: str = "default"
    markdown: str
    teaching_stage: str
    objective_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class SpeakerNote(BaseModel):
    slide_id: str
    explanation: str
    questions: list[str] = Field(default_factory=list)
    expected_answers: list[str] = Field(default_factory=list)
    transition: str
    board_notes: str
    estimated_minutes: int = Field(ge=0, le=120)


class Exercise(BaseModel):
    exercise_id: str
    level: Literal["基础", "巩固", "提高"]
    objective_ids: list[str] = Field(min_length=1)
    question: str
    type: str
    difficulty: int = Field(ge=1, le=5)
    answer: str
    explanation: str
    source: str
    needs_teacher_review: bool
    citations: list[Citation] = Field(default_factory=list)


class GenerationBundle(BaseModel):
    artifacts: dict[str, dict[str, Any]]
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model: str
    degraded: bool = False
    trace: TraceInfo | None = None

    @model_validator(mode="after")
    def require_four_artifacts(self):
        required = {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"}
        missing = required - set(self.artifacts)
        if missing:
            raise ValueError(f"缺少备课产物：{sorted(missing)}")
        return self


class SkillRequest(BaseModel):
    context: LessonContext
    instruction: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class SkillResponse(BaseModel):
    skill_id: str
    result: dict[str, Any]
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: TraceInfo
    degraded: bool = False
