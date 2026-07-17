from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import AITask
from app.schemas.api import TaskOut
from app.services.artifact_service import run_generation_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(AITask, task_id)
    if not task: raise HTTPException(404, "任务不存在")
    return task


@router.post("/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(AITask, task_id)
    if not task: raise HTTPException(404, "任务不存在")
    if task.status in {"succeeded", "failed"}: raise HTTPException(409, "已结束任务不能取消")
    task.status = "cancelled"; task.stage = "用户已取消"; db.commit(); db.refresh(task); return task


@router.post("/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    old = db.get(AITask, task_id)
    if not old: raise HTTPException(404, "任务不存在")
    if old.status not in {"failed", "cancelled"}: raise HTTPException(409, "只有失败或取消任务可以重试")
    task = AITask(project_id=old.project_id, type=old.type, trace_id=old.trace_id, idempotency_key=f"{old.idempotency_key}-retry-{old.updated_at.timestamp()}", input_snapshot=old.input_snapshot)
    db.add(task); db.commit(); db.refresh(task); background.add_task(run_generation_task, task.id); return task

