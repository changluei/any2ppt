"""项目、“我的演示”、主题准备和生成任务 API。

创建项目时登记并准备所选主题；生成请求使用幂等键避免重复点击创建多个
任务，并立即把长耗时工作交给后台执行。
"""

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
from app.repositories.projects import get_project, list_projects, project_delete_blockers
from app.schemas.api import ArtifactOut, ProjectCreate, ProjectOut, TaskCreate, TaskOut
from app.services.artifact_service import artifact_out, run_generation_task
from app.services.theme_service import delete_project_theme, get_theme, prepare_project_theme
from app.services.knowledge_base_service import ensure_knowledge_bases, validate_knowledge_base_ids
from app.models import SourceDocument
from app.ai.skills import SKILLS

router = APIRouter(prefix="/api/projects", tags=["projects"])
VALID_TASK_TYPES = {"full_lesson", *(item.id for item in SKILLS)}


@router.get("", response_model=list[ProjectOut])
def list_projects_route(db: Session = Depends(get_db)):
    """返回“我的演示”列表。"""
    return list_projects(db)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """创建项目、校验知识库选择，并准备所选 Slidev 主题。"""
    if not get_theme(data.theme_id):
        raise HTTPException(400, detail={"code": "THEME_NOT_FOUND", "message": "所选模板不存在或尚未通过兼容检查"})
    ensure_knowledge_bases(db)
    try:
        validate_knowledge_base_ids(db, data.knowledge_base_ids, require_ready=False)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "KNOWLEDGE_BASE_NOT_FOUND", "message": str(exc)}) from exc
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
    """返回项目详情。"""
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectCreate, db: Session = Depends(get_db)):
    """更新生成参数；主题变化时重新执行缓存准备。"""
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    if not get_theme(data.theme_id):
        raise HTTPException(400, detail={"code": "THEME_NOT_FOUND", "message": "所选模板不存在或尚未通过兼容检查"})
    try:
        validate_knowledge_base_ids(db, data.knowledge_base_ids, require_ready=False)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "KNOWLEDGE_BASE_NOT_FOUND", "message": str(exc)}) from exc
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
    """默认先返回关联对象统计，只有 force 才执行级联清理。"""
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
    db.query(SourceDocument).filter(SourceDocument.project_id == project_id).update(
        {SourceDocument.project_id: None},
        synchronize_session=False,
    )
    db.commit()
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
    """主题下载失败后手动重试，不需要重建项目。"""
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
    """冻结生成输入、创建幂等任务并安排后台生成。"""
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    if data.type not in VALID_TASK_TYPES:
        raise HTTPException(400, detail={"code": "UNKNOWN_TASK_TYPE", "message": "未知的生成任务类型"})
    requested_sources = list(data.selected_source_ids)
    if requested_sources:
        ready = {
            row[0]
            for row in db.query(SourceDocument.id).filter(
                SourceDocument.id.in_(requested_sources),
                SourceDocument.knowledge_base_id == "personal",
                SourceDocument.status == "ready",
            ).all()
        }
        missing = [source_id for source_id in requested_sources if source_id not in ready]
        if missing:
            raise HTTPException(
                409,
                detail={"code": "SOURCE_NOT_READY", "message": "选中的资料尚未完成索引", "source_ids": missing},
            )
    requested_libraries = list(data.selected_knowledge_base_ids or project.knowledge_base_ids or [])
    try:
        requested_libraries = validate_knowledge_base_ids(db, requested_libraries)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "KNOWLEDGE_BASE_NOT_FOUND", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(409, detail={"code": "KNOWLEDGE_BASE_NOT_READY", "message": str(exc)}) from exc
    existing = db.query(AITask).filter_by(project_id=project_id, idempotency_key=data.idempotency_key).first()
    if existing:
        return existing
    task = AITask(
        project_id=project_id,
        type=data.type,
        trace_id=getattr(request.state, "trace_id", str(uuid.uuid4())),
        idempotency_key=data.idempotency_key,
        input_snapshot={
            "selected_source_ids": requested_sources,
            "selected_knowledge_base_ids": requested_libraries,
            "teacher_requirements": data.teacher_requirements,
            "type": data.type,
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    background.add_task(run_generation_task, task.id)
    return task


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def recent_tasks(project_id: str, db: Session = Depends(get_db)):
    """列出项目最近任务，供生成页刷新后恢复进度。"""
    if not get_project(db, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return db.query(AITask).filter_by(project_id=project_id).order_by(AITask.created_at.desc()).limit(20).all()


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(project_id: str, db: Session = Depends(get_db)):
    """列出项目当前可编辑或导出的制品。"""
    if not get_project(db, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    artifacts = db.query(LessonArtifact).filter_by(project_id=project_id).all()
    return [artifact_out(artifact, artifact.versions[-1]) for artifact in artifacts if artifact.versions]
