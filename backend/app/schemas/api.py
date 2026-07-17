from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=40)
    grade: str = Field(min_length=1, max_length=40)
    textbook_version: str = Field(default="", max_length=80)
    lesson_topic: str = Field(min_length=1, max_length=160)
    lesson_count: int = Field(default=1, ge=1, le=8)
    student_profile: str = Field(default="", max_length=2000)
    teacher_requirements: str = Field(default="", max_length=3000)


class ProjectOut(ProjectCreate, ORMModel):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime


class SourceOut(ORMModel):
    id: str
    project_id: str
    original_name: str
    media_type: str
    size: int
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    source_ids: Optional[list[str]] = None


class SearchResult(BaseModel):
    content: str
    source_id: str
    chunk_id: str
    filename: str
    location: str
    score: float


class TaskCreate(BaseModel):
    type: str
    selected_source_ids: list[str] = []
    teacher_requirements: str = ""
    idempotency_key: str = Field(min_length=3, max_length=100)


class TaskOut(ORMModel):
    id: str
    project_id: str
    type: str
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    stage: str
    progress: int
    trace_id: str
    result_artifact_id: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class ArtifactOut(BaseModel):
    artifact_id: str
    version_id: str
    project_id: str
    type: str
    version_no: int
    content: dict[str, Any]
    citations: list[dict[str, Any]]
    warnings: list[str]
    created_at: datetime


class RevisionRequest(BaseModel):
    base_version_no: int = Field(ge=1)
    target_type: str
    target_id: str
    instruction: str = Field(min_length=2, max_length=1000)
    sync_related: bool = False


class HumanDecision(BaseModel):
    decision: Literal["accept", "revise", "cancel"]


class ExportCreate(BaseModel):
    package_type: Literal["teacher", "student"]
