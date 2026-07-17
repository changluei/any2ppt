from typing import Any
from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    filename: str
    location: str
    quote: str


class LessonContext(BaseModel):
    project_id: str
    subject: str
    grade: str
    textbook_version: str = ""
    lesson_topic: str
    lesson_count: int = 1
    student_profile: str = ""
    selected_source_ids: list[str] = []
    teacher_requirements: str = ""


class GenerationBundle(BaseModel):
    artifacts: dict[str, dict[str, Any]]
    citations: list[Citation] = []
    warnings: list[str] = []
    model: str
    degraded: bool = False

