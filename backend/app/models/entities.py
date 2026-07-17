from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def uid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(40))
    grade: Mapped[str] = mapped_column(String(40))
    textbook_version: Mapped[str] = mapped_column(String(80), default="")
    lesson_topic: Mapped[str] = mapped_column(String(160))
    lesson_count: Mapped[int] = mapped_column(Integer, default=1)
    student_profile: Mapped[str] = mapped_column(Text, default="")
    teacher_requirements: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    sources = relationship("SourceDocument", cascade="all, delete-orphan")


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("project_id", "sha256", name="uq_project_source_hash"), Index("ix_source_project_status", "project_id", "status"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80))
    media_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="uploaded")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AITask(Base, TimestampMixin):
    __tablename__ = "ai_tasks"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_task_idempotency"), Index("ix_task_project_created", "project_id", "created_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="等待执行")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_artifact_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class LessonArtifact(Base, TimestampMixin):
    __tablename__ = "lesson_artifacts"
    __table_args__ = (UniqueConstraint("project_id", "type", name="uq_project_artifact_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    current_version_no: Mapped[int] = mapped_column(Integer, default=0)
    versions = relationship("ArtifactVersion", cascade="all, delete-orphan", order_by="ArtifactVersion.version_no")


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version_no", name="uq_artifact_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("lesson_artifacts.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    change_type: Mapped[str] = mapped_column(String(32), default="generated")
    changed_ids: Mapped[list] = mapped_column(JSON, default=list)
    content: Mapped[dict] = mapped_column(JSON)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GraphRun(Base, TimestampMixin):
    __tablename__ = "graph_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    current_node: Mapped[str] = mapped_column(String(64), default="analyze_sources")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[dict] = mapped_column(JSON, default=dict)
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    human_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class ExportJob(Base, TimestampMixin):
    __tablename__ = "export_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    package_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
