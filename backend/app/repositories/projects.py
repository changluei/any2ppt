from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import AITask, ExportJob, GraphRun, LessonArtifact, Project, ProjectImage, SourceDocument


def list_projects(session: Session) -> list[Project]:
    return session.query(Project).order_by(Project.updated_at.desc()).all()


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def project_delete_blockers(session: Session, project_id: str) -> dict[str, int]:
    return {
        "sources": session.query(SourceDocument).filter(SourceDocument.project_id == project_id).count(),
        "images": session.query(ProjectImage).filter(ProjectImage.project_id == project_id).count(),
        "tasks": session.query(AITask).filter(AITask.project_id == project_id).count(),
        "artifacts": session.query(LessonArtifact).filter(LessonArtifact.project_id == project_id).count(),
        "graphs": session.query(GraphRun).filter(GraphRun.project_id == project_id).count(),
        "exports": session.query(ExportJob).filter(ExportJob.project_id == project_id).count(),
    }


def ready_source_ids(session: Session, project_id: str, source_ids: Iterable[str] | None = None) -> list[str]:
    query = session.query(SourceDocument.id).filter(
        SourceDocument.project_id == project_id,
        SourceDocument.status == "ready",
    )
    if source_ids:
        query = query.filter(SourceDocument.id.in_(list(source_ids)))
    return [row[0] for row in query.all()]
