from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def uid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_status_updated", "status", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    grade: Mapped[str] = mapped_column(String(40), nullable=False)
    textbook_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    lesson_topic: Mapped[str] = mapped_column(String(160), nullable=False)
    lesson_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    student_profile: Mapped[str] = mapped_column(Text, default="", nullable=False)
    teacher_requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True, nullable=False)

    sources = relationship("SourceDocument", cascade="all, delete-orphan", passive_deletes=True)
    tasks = relationship("AITask", cascade="all, delete-orphan", passive_deletes=True)
    artifacts = relationship("LessonArtifact", cascade="all, delete-orphan", passive_deletes=True)
    graphs = relationship("GraphRun", cascade="all, delete-orphan", passive_deletes=True)
    exports = relationship("ExportJob", cascade="all, delete-orphan", passive_deletes=True)


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_project_source_hash"),
        Index("ix_source_project_status", "project_id", "status"),
        Index("ix_source_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AITask(Base, TimestampMixin):
    __tablename__ = "ai_tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_task_idempotency"),
        Index("ix_task_project_created", "project_id", "created_at"),
        Index("ix_task_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), default="waiting", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result_artifact_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class LessonArtifact(Base, TimestampMixin):
    __tablename__ = "lesson_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "type", name="uq_project_artifact_type"),
        Index("ix_artifact_project_type", "project_id", "type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    current_version_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    versions = relationship(
        "ArtifactVersion",
        cascade="all, delete-orphan",
        order_by="ArtifactVersion.version_no",
        back_populates="artifact",
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version_no", name="uq_artifact_version"),
        Index("ix_artifact_version_artifact_no", "artifact_id", "version_no"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("lesson_artifacts.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    change_type: Mapped[str] = mapped_column(String(32), default="generated", nullable=False)
    changed_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    artifact = relationship("LessonArtifact", back_populates="versions")


class GraphRun(Base, TimestampMixin):
    __tablename__ = "graph_runs"
    __table_args__ = (
        Index("ix_graph_project_status", "project_id", "status"),
        Index("ix_graph_task", "task_id"),
        Index("ix_graph_thread", "thread_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("ai_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(80), default=uid, index=True, nullable=False)
    checkpoint_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_node: Mapped[str] = mapped_column(String(64), default="analyze_sources", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    attempts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    nodes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    issues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    human_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class ExportJob(Base, TimestampMixin):
    __tablename__ = "export_jobs"
    __table_args__ = (Index("ix_export_project_status", "project_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    package_type: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_versions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
