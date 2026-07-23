from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.ai.graph import NODES
from app.core.config import get_settings
from app.core.database import get_db
from app.models import AITask, ArtifactVersion, ExportJob, GraphRun, LessonArtifact, Project
from app.schemas.api import ExportCreate, GraphRunOut, GraphStartRequest, HumanDecision
from app.services.export_service import create_export
from app.services.graph_service import create_graph_run, decide_graph, execute_graph_run, resume_graph_run

router = APIRouter(prefix="/api", tags=["workflow"])

EXPORT_REQUIRED_TYPES = {
    "teacher": {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"},
    "student": {"slide_deck", "exercise_set"},
    "pptx": {"slide_deck"},
}


def resolve_export_versions(
    db: Session,
    project_id: str,
    package_type: str,
    version_ids: list[str],
) -> dict[str, str]:
    selected: dict[str, ArtifactVersion] = {}
    unique_version_ids = list(dict.fromkeys(version_ids))
    if unique_version_ids:
        versions = (
            db.query(ArtifactVersion)
            .join(LessonArtifact, ArtifactVersion.artifact_id == LessonArtifact.id)
            .filter(
                LessonArtifact.project_id == project_id,
                ArtifactVersion.id.in_(unique_version_ids),
            )
            .all()
        )
        if len(versions) != len(unique_version_ids):
            raise HTTPException(
                404,
                detail={"code": "VERSION_NOT_FOUND", "message": "导出版本不存在或不属于当前项目"},
            )
        for version in versions:
            artifact_type = version.artifact.type
            if artifact_type in selected:
                raise HTTPException(
                    409,
                    detail={
                        "code": "EXPORT_VERSION_CONFLICT",
                        "message": "同一类产物只能选择一个版本导出",
                    },
                )
            selected[artifact_type] = version
    else:
        artifacts = db.query(LessonArtifact).filter_by(project_id=project_id).all()
        for artifact in artifacts:
            if artifact.versions:
                selected[artifact.type] = artifact.versions[-1]

    required = EXPORT_REQUIRED_TYPES[package_type]
    missing = sorted(required - selected.keys())
    if missing:
        raise HTTPException(
            409,
            detail={
                "code": "EXPORT_ARTIFACTS_MISSING",
                "message": "导出所需产物版本不完整",
                "details": {"missing_types": missing},
            },
        )
    return {artifact_type: selected[artifact_type].id for artifact_type in sorted(required)}


def graph_payload(graph: GraphRun) -> dict:
    return {
        "id": graph.id,
        "project_id": graph.project_id,
        "task_id": graph.task_id,
        "thread_id": graph.thread_id,
        "checkpoint_ref": graph.checkpoint_ref,
        "attempt": graph.attempt,
        "status": graph.status,
        "current_node": graph.current_node,
        "nodes": graph.nodes,
        "issues": graph.issues,
        "state_snapshot": graph.state_snapshot,
        "human_decision": graph.human_decision,
        "created_at": graph.created_at,
        "updated_at": graph.updated_at,
    }


def graph_or_404(db: Session, graph_id: str) -> GraphRun:
    graph = db.get(GraphRun, graph_id)
    if not graph:
        raise HTTPException(404, detail={"code": "GRAPH_NOT_FOUND", "message": "流程不存在"})
    return graph


@router.post("/projects/{project_id}/graph/runs", response_model=GraphRunOut, status_code=202)
def start_graph(
    project_id: str,
    data: GraphStartRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    task = None
    if data.task_id:
        task = db.get(AITask, data.task_id)
        if not task or task.project_id != project_id:
            raise HTTPException(404, detail={"code": "TASK_NOT_FOUND", "message": "任务不存在"})
    else:
        task = db.query(AITask).filter_by(project_id=project_id).order_by(AITask.created_at.desc()).first()
    if not task:
        raise HTTPException(409, detail={"code": "TASK_REQUIRED", "message": "需要先创建一个任务"})
    graph = create_graph_run(
        db,
        project,
        task,
        thread_id=data.thread_id or task.trace_id or str(uuid.uuid4()),
        checkpoint_ref=data.checkpoint_ref or f"task:{task.id}",
    )
    graph.status = "running"
    db.commit()
    payload = graph_payload(graph)
    background.add_task(execute_graph_run, graph.id, resume_from="analyze_sources")
    return payload


@router.get("/projects/{project_id}/graph")
def get_graph(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    graph = db.query(GraphRun).filter_by(project_id=project_id).order_by(GraphRun.created_at.desc()).first()
    if not graph:
        return {"status": "not_started", "nodes": [], "issues": [], "current_node": None}
    return graph_payload(graph)


@router.post("/graphs/{graph_id}/cancel")
def cancel_graph(graph_id: str, db: Session = Depends(get_db)):
    graph = graph_or_404(db, graph_id)
    if graph.status in {"succeeded", "failed"}:
        return graph_payload(graph)
    graph.status = "cancelled"
    graph.current_node = "cancelled"
    state = dict(graph.state_snapshot or {})
    state["resume_from"] = state.get("current_node") or "analyze_sources"
    state["current_node"] = "cancelled"
    state["cancelled"] = True
    graph.state_snapshot = state
    task = db.get(AITask, graph.task_id)
    if task and task.status in {"pending", "running"}:
        task.status = "cancelled"
        task.stage = "用户已取消"
    db.commit()
    db.refresh(graph)
    return graph_payload(graph)


@router.post("/graphs/{graph_id}/resume", response_model=GraphRunOut)
def resume_graph(graph_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    graph = graph_or_404(db, graph_id)
    if graph.status not in {"cancelled", "failed", "needs_revision", "awaiting_confirmation"}:
        raise HTTPException(409, detail={"code": "GRAPH_CONFLICT", "message": "当前流程不需要恢复"})
    graph.attempt += 1
    graph.status = "running"
    state = dict(graph.state_snapshot or {})
    resume_from = state.get("resume_from") or state.get("current_node") or "analyze_sources"
    if resume_from not in NODES or resume_from in {"human_confirm", "finalize"}:
        resume_from = "analyze_sources"
    state.update(
        {
            "resume_from": resume_from,
            "current_node": resume_from,
            "cancelled": False,
            "failed": False,
            "error": "",
            "human_decision": None,
        }
    )
    graph.current_node = resume_from
    graph.human_decision = None
    graph.state_snapshot = state
    db.commit()
    db.refresh(graph)
    payload = graph_payload(graph)
    background.add_task(resume_graph_run, graph.id, resume_from=resume_from)
    return payload


@router.post("/graphs/{graph_id}/confirm")
def confirm_graph(graph_id: str, data: HumanDecision, db: Session = Depends(get_db)):
    graph = graph_or_404(db, graph_id)
    if graph.human_decision == data.decision and graph.status in {"succeeded", "cancelled"}:
        return graph_payload(graph)
    if graph.status not in {"awaiting_confirmation", "needs_revision"}:
        raise HTTPException(409, detail={"code": "GRAPH_CONFLICT", "message": "当前流程不在人工确认节点"})
    graph.human_decision = data.decision
    graph.status = "running"
    state = dict(graph.state_snapshot or {})
    state["human_decision"] = data.decision
    state["resume_from"] = "human_confirm"
    state["cancelled"] = False
    graph.state_snapshot = state
    db.commit()
    decide_graph(graph.id, data.decision)
    db.expire_all()
    graph = graph_or_404(db, graph_id)
    return graph_payload(graph)


@router.post("/projects/{project_id}/exports", status_code=202)
def export_project(project_id: str, data: ExportCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    graph = db.query(GraphRun).filter_by(project_id=project_id, status="succeeded").first()
    if not graph:
        raise HTTPException(409, detail={"code": "GRAPH_NOT_READY", "message": "请先完成人工确认"})
    selected_versions = resolve_export_versions(db, project_id, data.package_type, data.artifact_version_ids)
    job = ExportJob(
        project_id=project_id,
        package_type=data.package_type,
        selected_versions=selected_versions,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(create_export, job.id)
    return {"job_id": job.id, "status": job.status, "selected_versions": job.selected_versions}


@router.get("/exports/{job_id}")
def export_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ExportJob, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "EXPORT_NOT_FOUND", "message": "导出任务不存在"})
    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "package_type": job.package_type,
        "selected_versions": job.selected_versions,
        "status": job.status,
        "error_message": job.error_message,
        "download_url": f"/api/exports/{job.id}/download" if job.status == "succeeded" else None,
    }


@router.get("/exports/{job_id}/download")
def download_export(job_id: str, project_id: str | None = None, db: Session = Depends(get_db)):
    job = db.get(ExportJob, job_id)
    if not job or job.status != "succeeded" or not job.file_path:
        raise HTTPException(404, detail={"code": "EXPORT_NOT_READY", "message": "导出文件尚不可用"})
    if project_id and job.project_id != project_id:
        raise HTTPException(404, detail={"code": "EXPORT_NOT_FOUND", "message": "导出任务不存在"})
    path = Path(job.file_path)
    export_root = get_settings().export_dir.resolve()
    resolved = path.resolve()
    if export_root not in resolved.parents and resolved != export_root:
        raise HTTPException(403, detail={"code": "EXPORT_PATH_BLOCKED", "message": "导出文件路径不合法"})
    if not resolved.is_file():
        raise HTTPException(410, detail={"code": "EXPORT_EXPIRED", "message": "导出文件已过期"})
    if job.package_type == "pptx":
        return FileResponse(
            resolved,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="备课课件.pptx",
        )
    return FileResponse(resolved, media_type="application/zip", filename=f"LessonDeck-{job.package_type}.zip")
