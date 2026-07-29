"""关系数据库实体定义。

MySQL 保存业务事实和版本元数据，真正的向量与文本片段由 Chroma 保存。
这里的外键和唯一约束同时承担并发保护：例如同一项目同一制品类型只能有
一条 LessonArtifact，但它可以拥有多个不可变 ArtifactVersion。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def uid() -> str:
    """生成可跨数据库使用的 UUID 字符串主键。"""
    return str(uuid.uuid4())


class TimestampMixin:
    """为可变业务实体提供统一的创建/更新时间。"""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Project(Base, TimestampMixin):
    """一次 PPT 生成/编辑工作的根聚合，关联资料、任务、制品和导出。"""
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
    theme_id: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    theme_status: Mapped[str] = mapped_column(String(24), default="selected", nullable=False)
    knowledge_base_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True, nullable=False)

    sources = relationship("SourceDocument", passive_deletes=True)
    images = relationship("ProjectImage", cascade="all, delete-orphan", passive_deletes=True)
    tasks = relationship("AITask", cascade="all, delete-orphan", passive_deletes=True)
    artifacts = relationship("LessonArtifact", cascade="all, delete-orphan", passive_deletes=True)
    graphs = relationship("GraphRun", cascade="all, delete-orphan", passive_deletes=True)
    exports = relationship("ExportJob", cascade="all, delete-orphan", passive_deletes=True)
    agent_messages = relationship("EditorAgentMessage", cascade="all, delete-orphan", passive_deletes=True)


class KnowledgeBase(Base, TimestampMixin):
    """知识库目录；官方三库只读，personal 库由用户上传持续丰富。"""
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        Index("ix_knowledge_base_kind", "kind"),
        Index("ix_knowledge_base_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="empty", nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sources = relationship("SourceDocument", back_populates="knowledge_base")


class SourceDocument(Base, TimestampMixin):
    """上传资料的文件元数据；解析后的 chunks 不存 MySQL，而存向量库。"""
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "sha256", name="uq_knowledge_base_source_hash"),
        Index("ix_source_project_status", "project_id", "status"),
        Index("ix_source_project_created", "project_id", "created_at"),
        Index("ix_source_library_status", "knowledge_base_id", "status"),
        Index("ix_source_library_created", "knowledge_base_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="RESTRICT"),
        default="personal",
        index=True,
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    knowledge_base = relationship("KnowledgeBase", back_populates="sources")


class ProjectImage(Base, TimestampMixin):
    """项目图片资产；保存尺寸便于生成 Slidev 定位代码，不做图片语义识别。"""
    __tablename__ = "project_images"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_project_image_hash"),
        Index("ix_project_image_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)


class EditorAgentMessage(Base):
    """工作台 ReAct 对话历史，包含工具轨迹和对应的制品版本号。"""
    __tablename__ = "editor_agent_messages"
    __table_args__ = (
        Index("ix_editor_agent_project_created", "project_id", "created_at"),
        Index("ix_editor_agent_trace", "trace_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("project_images.id", ondelete="SET NULL"),
        nullable=True,
    )
    image_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    tool_trace: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    artifact_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AITask(Base, TimestampMixin):
    """可重试、可取消的长耗时 AI 任务及其输入/结果快照。"""
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
    """课件、教案或习题等逻辑制品的版本指针。"""
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
    """不可变的制品快照；父版本与 changed_ids 支持审计和回滚。"""
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
    """一次 LangGraph 生成运行的节点进度、检查点和人工确认状态。"""
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
    """异步导出作业，记录所选制品版本与最终文件位置。"""
    __tablename__ = "export_jobs"
    __table_args__ = (Index("ix_export_project_status", "project_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    package_type: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_versions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
