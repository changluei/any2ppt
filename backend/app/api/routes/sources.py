from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.ai.vector_store import ProjectVectorStore
from app.core.database import get_db
from app.models import Project, SourceDocument
from app.schemas.api import SearchRequest, SearchResult, SourceOut
from app.services.source_service import delete_source, index_source, save_upload

router = APIRouter(prefix="/api/projects/{project_id}", tags=["sources"])


def source_or_404(db: Session, project_id: str, source_id: str) -> SourceDocument:
    source = db.query(SourceDocument).filter_by(id=source_id, project_id=project_id).first()
    if not source:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "资料不存在"})
    return source


@router.post("/sources", response_model=SourceOut, status_code=201)
async def upload_source(
    project_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    try:
        source = save_upload(db, project_id, file.filename or "unnamed", file.content_type or "", await file.read())
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_SOURCE_FILE", "message": str(exc)}) from exc
    background.add_task(index_source, source.id)
    return source


@router.get("/sources", response_model=list[SourceOut])
def list_sources(project_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return db.query(SourceDocument).filter_by(project_id=project_id).order_by(SourceDocument.created_at.desc()).all()


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    return source_or_404(db, project_id, source_id)


@router.post("/sources/{source_id}/index", response_model=SourceOut)
def retry_index(project_id: str, source_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    source = source_or_404(db, project_id, source_id)
    source.status = "uploaded"
    source.error_message = None
    db.commit()
    db.refresh(source)
    background.add_task(index_source, source.id)
    return source


@router.delete("/sources/{source_id}", status_code=204)
def remove_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    source = source_or_404(db, project_id, source_id)
    try:
        delete_source(db, source)
    except RuntimeError as exc:
        raise HTTPException(
            503,
            detail={"code": str(exc), "message": "资料删除未完成，已记录可重试错误"},
        ) from exc


@router.post("/search", response_model=list[SearchResult])
def search(project_id: str, data: SearchRequest, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    if not db.query(SourceDocument).filter_by(project_id=project_id, status="ready").first():
        raise HTTPException(409, detail={"code": "SOURCE_NOT_READY", "message": "没有已完成索引的资料"})
    return ProjectVectorStore().similarity_search(project_id, data.query, data.top_k, data.source_ids)
