from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Project, SourceDocument
from app.schemas.api import SourceOut, SearchRequest, SearchResult
from app.services.source_service import save_upload, index_source, delete_source
from app.ai.vector_store import ProjectVectorStore

router = APIRouter(prefix="/api/projects/{project_id}", tags=["sources"])


def source_or_404(db: Session, project_id: str, source_id: str) -> SourceDocument:
    source = db.query(SourceDocument).filter_by(id=source_id, project_id=project_id).first()
    if not source: raise HTTPException(404, "资料不存在")
    return source


@router.post("/sources", response_model=SourceOut, status_code=201)
async def upload_source(project_id: str, background: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not db.get(Project, project_id): raise HTTPException(404, "项目不存在")
    try: source = save_upload(db, project_id, file.filename or "unnamed", file.content_type or "", await file.read())
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    background.add_task(index_source, source.id)
    return source


@router.get("/sources", response_model=list[SourceOut])
def list_sources(project_id: str, db: Session = Depends(get_db)):
    return db.query(SourceDocument).filter_by(project_id=project_id).order_by(SourceDocument.created_at.desc()).all()


@router.post("/sources/{source_id}/index", response_model=SourceOut)
def retry_index(project_id: str, source_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    source = source_or_404(db, project_id, source_id); source.status = "uploaded"; source.error_message = None; db.commit(); background.add_task(index_source, source.id); return source


@router.delete("/sources/{source_id}", status_code=204)
def remove_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    delete_source(db, source_or_404(db, project_id, source_id))


@router.post("/search", response_model=list[SearchResult])
def search(project_id: str, data: SearchRequest, db: Session = Depends(get_db)):
    if not db.query(SourceDocument).filter_by(project_id=project_id, status="ready").first(): raise HTTPException(409, "没有已完成索引的资料")
    return ProjectVectorStore().similarity_search(project_id, data.query, data.top_k, data.source_ids)

