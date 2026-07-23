from __future__ import annotations

import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.ai.vector_store import ProjectVectorStore
from app.core.config import get_settings
from app.core.database import get_db
from app.models import AITask, ExportJob, LessonArtifact, Project
from app.repositories.projects import get_project, list_projects, project_delete_blockers, ready_source_ids
from app.schemas.api import ArtifactOut, ProjectCreate, ProjectOut, TaskCreate, TaskOut
from app.services.artifact_service import artifact_out, run_generation_task
from app.services.theme_service import delete_project_theme, get_theme, prepare_project_theme
from app.ai.skills import SKILLS

router = APIRouter(prefix="/api/projects", tags=["projects"])
VALID_TASK_TYPES = {"full_lesson", *(item.id for item in SKILLS)}


@router.get("", response_model=list[ProjectOut])
def list_projects_route(db: Session = Depends(get_db)):
    return list_projects(db)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    if not get_theme(data.theme_id):
        raise HTTPException(400, detail={"code": "THEME_NOT_FOUND", "message": "所选模板不存在或尚未通过兼容检查"})
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    try:
        prepare_project_theme(project.id, project.theme_id)
        project.theme_status = "ready"
    except Exception:
        project.theme_status = "failed"
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_route(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectCreate, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    if not get_theme(data.theme_id):
        raise HTTPException(400, detail={"code": "THEME_NOT_FOUND", "message": "所选模板不存在或尚未通过兼容检查"})
    theme_changed = project.theme_id != data.theme_id
    for key, value in data.model_dump().items():
        setattr(project, key, value)
    if theme_changed:
        project.theme_status = "selected"
    db.commit()
    if theme_changed:
        try:
            prepare_project_theme(project.id, project.theme_id)
            project.theme_status = "ready"
        except Exception:
            project.theme_status = "failed"
        db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, force: bool = Query(False), db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    blockers = project_delete_blockers(db, project_id)
    if any(count for count in blockers.values()) and not force:
        raise HTTPException(
            409,
            detail={"code": "PROJECT_NOT_EMPTY", "message": "项目包含资料或课件，需要确认后才能删除", "blockers": blockers},
        )
    active_tasks = db.query(AITask).filter(
        AITask.project_id == project_id,
        AITask.status.in_(["pending", "running"]),
    ).count()
    if active_tasks:
        raise HTTPException(409, detail={"code": "PROJECT_BUSY", "message": "项目正在生成中，请完成或取消任务后再删除"})
    settings = get_settings()
    export_paths = [
        Path(row.file_path)
        for row in db.query(ExportJob).filter_by(project_id=project_id).all()
        if row.file_path
    ]
    db.delete(project)
    db.commit()
    try:
        ProjectVectorStore().delete_project(project_id)
    except Exception:
        pass
    upload_root = settings.upload_dir.resolve()
    upload_target = (upload_root / project_id).resolve()
    if upload_target.parent == upload_root:
        shutil.rmtree(upload_target, ignore_errors=True)
    export_root = settings.export_dir.resolve()
    for export_path in export_paths:
        resolved = export_path.resolve()
        if resolved.parent == export_root:
            resolved.unlink(missing_ok=True)
    delete_project_theme(project_id)


@router.post("/{project_id}/theme/prepare", response_model=ProjectOut)
def retry_project_theme(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    project.theme_status = "preparing"
    db.commit()
    try:
        prepare_project_theme(project.id, project.theme_id)
        project.theme_status = "ready"
    except Exception as exc:
        project.theme_status = "failed"
        db.commit()
        raise HTTPException(502, detail={"code": "THEME_DOWNLOAD_FAILED", "message": f"模板下载失败：{str(exc)[:160]}"}) from exc
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/tasks", response_model=TaskOut, status_code=202)
def create_task(project_id: str, data: TaskCreate, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    if data.type not in VALID_TASK_TYPES:
        raise HTTPException(400, detail={"code": "UNKNOWN_TASK_TYPE", "message": "未知的生成任务类型"})
    requested_sources = list(data.selected_source_ids)
    if requested_sources:
        ready = set(ready_source_ids(db, project_id, requested_sources))
        missing = [source_id for source_id in requested_sources if source_id not in ready]
        if missing:
            raise HTTPException(
                409,
                detail={"code": "SOURCE_NOT_READY", "message": "选中的资料尚未完成索引", "source_ids": missing},
            )
    existing = db.query(AITask).filter_by(project_id=project_id, idempotency_key=data.idempotency_key).first()
    if existing:
        return existing
    task = AITask(
        project_id=project_id,
        type=data.type,
        trace_id=getattr(request.state, "trace_id", str(uuid.uuid4())),
        idempotency_key=data.idempotency_key,
        input_snapshot={"selected_source_ids": requested_sources, "teacher_requirements": data.teacher_requirements, "type": data.type},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    background.add_task(run_generation_task, task.id)
    return task


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def recent_tasks(project_id: str, db: Session = Depends(get_db)):
    if not get_project(db, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return db.query(AITask).filter_by(project_id=project_id).order_by(AITask.created_at.desc()).limit(20).all()


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(project_id: str, db: Session = Depends(get_db)):
    if not get_project(db, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    artifacts = db.query(LessonArtifact).filter_by(project_id=project_id).all()
    return [artifact_out(artifact, artifact.versions[-1]) for artifact in artifacts if artifact.versions]
