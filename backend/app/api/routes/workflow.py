from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import GraphRun, ExportJob, Project
from app.schemas.api import HumanDecision, ExportCreate
from app.services.export_service import create_export

router = APIRouter(prefix="/api", tags=["workflow"])


@router.get("/projects/{project_id}/graph")
def get_graph(project_id: str, db: Session = Depends(get_db)):
    graph = db.query(GraphRun).filter_by(project_id=project_id).order_by(GraphRun.created_at.desc()).first()
    if not graph: return {"status": "not_started", "nodes": [], "issues": []}
    return {"id": graph.id, "project_id": graph.project_id, "task_id": graph.task_id, "status": graph.status, "current_node": graph.current_node, "nodes": graph.nodes, "issues": graph.issues, "human_decision": graph.human_decision}


@router.post("/graphs/{graph_id}/confirm")
def confirm_graph(graph_id: str, data: HumanDecision, db: Session = Depends(get_db)):
    graph = db.get(GraphRun, graph_id)
    if not graph: raise HTTPException(404, "流程不存在")
    if graph.human_decision == data.decision: return {"status": graph.status, "decision": graph.human_decision}
    graph.human_decision = data.decision
    if data.decision == "accept":
        graph.status = "succeeded"; graph.current_node = "finalize"
    elif data.decision == "cancel": graph.status = "cancelled"
    else: graph.status = "needs_revision"
    db.commit(); return {"status": graph.status, "decision": graph.human_decision}


@router.post("/projects/{project_id}/exports", status_code=202)
def export_project(project_id: str, data: ExportCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Project, project_id): raise HTTPException(404, "项目不存在")
    graph = db.query(GraphRun).filter_by(project_id=project_id, status="succeeded").first()
    if not graph: raise HTTPException(409, "请先完成人工确认")
    job = ExportJob(project_id=project_id, package_type=data.package_type); db.add(job); db.commit(); db.refresh(job); background.add_task(create_export, job.id)
    return {"job_id": job.id, "status": job.status}


@router.get("/exports/{job_id}")
def export_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ExportJob, job_id)
    if not job: raise HTTPException(404, "导出任务不存在")
    return {"job_id": job.id, "project_id": job.project_id, "package_type": job.package_type, "status": job.status, "error_message": job.error_message, "download_url": f"/api/exports/{job.id}/download" if job.status == "succeeded" else None}


@router.get("/exports/{job_id}/download")
def download_export(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ExportJob, job_id)
    if not job or job.status != "succeeded" or not job.file_path: raise HTTPException(404, "导出文件尚不可用")
    path = Path(job.file_path)
    if not path.is_file(): raise HTTPException(410, "导出文件已过期")
    return FileResponse(path, media_type="application/zip", filename=f"LessonDeck-{job.package_type}.zip")

