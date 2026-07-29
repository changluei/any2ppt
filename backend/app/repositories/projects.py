"""项目聚合的只读查询助手。

Repository 只表达数据库查询，不发起 AI、文件或网络操作；事务提交由调用它
的 service/route 决定。这样删除检查和资料筛选可以在多条 API 中复用。
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import AITask, ExportJob, GraphRun, LessonArtifact, Project, ProjectImage, SourceDocument


def list_projects(session: Session) -> list[Project]:
    """按最近修改时间列出“我的演示”。"""
    return session.query(Project).order_by(Project.updated_at.desc()).all()


def get_project(session: Session, project_id: str) -> Project | None:
    """按主键取项目，不存在时返回 None 交由路由决定错误码。"""
    return session.get(Project, project_id)


def project_delete_blockers(session: Session, project_id: str) -> dict[str, int]:
    """统计级联删除会影响的对象，供非 force 删除给出明确提示。"""
    return {
        "sources": session.query(SourceDocument).filter(SourceDocument.project_id == project_id).count(),
        "images": session.query(ProjectImage).filter(ProjectImage.project_id == project_id).count(),
        "tasks": session.query(AITask).filter(AITask.project_id == project_id).count(),
        "artifacts": session.query(LessonArtifact).filter(LessonArtifact.project_id == project_id).count(),
        "graphs": session.query(GraphRun).filter(GraphRun.project_id == project_id).count(),
        "exports": session.query(ExportJob).filter(ExportJob.project_id == project_id).count(),
    }


def ready_source_ids(session: Session, project_id: str, source_ids: Iterable[str] | None = None) -> list[str]:
    """仅返回已完成解析/入库且属于当前项目的资料 ID。"""
    query = session.query(SourceDocument.id).filter(
        SourceDocument.project_id == project_id,
        SourceDocument.status == "ready",
    )
    if source_ids:
        query = query.filter(SourceDocument.id.in_(list(source_ids)))
    return [row[0] for row in query.all()]
