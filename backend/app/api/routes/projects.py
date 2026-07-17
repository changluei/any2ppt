import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Project, AITask, LessonArtifact
from app.schemas.api import ProjectCreate, ProjectOut, TaskCreate, TaskOut, ArtifactOut
from app.services.artifact_service import run_generation_task, artifact_out

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.updated_at.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**data.model_dump()); db.add(project); db.commit(); db.refresh(project); return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, "项目不存在")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectCreate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, "项目不存在")
    for key, value in data.model_dump().items(): setattr(project, key, value)
    db.commit(); db.refresh(project); return project


@router.post("/{project_id}/tasks", response_model=TaskOut, status_code=202)
def create_task(project_id: str, data: TaskCreate, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Project, project_id): raise HTTPException(404, "项目不存在")
    existing = db.query(AITask).filter_by(project_id=project_id, idempotency_key=data.idempotency_key).first()
    if existing: return existing
    task = AITask(project_id=project_id, type=data.type, trace_id=getattr(request.state, "trace_id", str(uuid.uuid4())), idempotency_key=data.idempotency_key, input_snapshot=data.model_dump())
    db.add(task); db.commit(); db.refresh(task); background.add_task(run_generation_task, task.id); return task


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def recent_tasks(project_id: str, db: Session = Depends(get_db)):
    return db.query(AITask).filter_by(project_id=project_id).order_by(AITask.created_at.desc()).limit(20).all()


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(project_id: str, db: Session = Depends(get_db)):
    artifacts = db.query(LessonArtifact).filter_by(project_id=project_id).all()
    return [artifact_out(a, a.versions[-1]) for a in artifacts if a.versions]

