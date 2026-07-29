"""兼容项目级资料的上传与检索 API。

上传内容会自动归档到 personal 知识库，同时保留 project_id 作为最初上传
来源，既能持续复用，也兼容旧版按项目资料筛选的调用。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Project, SourceDocument
from app.schemas.api import SearchRequest, SearchResult, SourceOut
from app.services.knowledge_base_service import search_knowledge_bases
from app.services.source_service import delete_source, index_source, save_upload

router = APIRouter(prefix="/api/projects/{project_id}", tags=["sources"])


def source_or_404(db: Session, project_id: str, source_id: str) -> SourceDocument:
    """校验资料确实属于当前项目，避免跨项目访问。"""
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
    """保存项目资料并安排后台入库。"""
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    try:
        source = save_upload(db, project_id, file.filename or "unnamed", file.content_type or "", await file.read())
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_SOURCE_FILE", "message": str(exc)}) from exc
    if source.status != "ready":
        background.add_task(index_source, source.id)
    return source


@router.get("/sources", response_model=list[SourceOut])
def list_sources(project_id: str, db: Session = Depends(get_db)):
    """列出该项目最初上传的资料。"""
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    return db.query(SourceDocument).filter_by(project_id=project_id).order_by(SourceDocument.created_at.desc()).all()


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    """读取单份项目资料状态。"""
    return source_or_404(db, project_id, source_id)


@router.post("/sources/{source_id}/index", response_model=SourceOut)
def retry_index(project_id: str, source_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    """重试失败或中断的解析与向量化。"""
    source = source_or_404(db, project_id, source_id)
    source.status = "uploaded"
    source.error_message = None
    db.commit()
    db.refresh(source)
    background.add_task(index_source, source.id)
    return source


@router.delete("/sources/{source_id}", status_code=204)
def remove_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    """删除项目资料及其向量记录。"""
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
    """在项目资料或显式选择的知识库范围内检索。"""
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    if not db.query(SourceDocument).filter_by(project_id=project_id, status="ready").first():
        raise HTTPException(409, detail={"code": "SOURCE_NOT_READY", "message": "没有已完成索引的资料"})
    source_ids = data.source_ids or [
        row[0]
        for row in db.query(SourceDocument.id).filter_by(
            project_id=project_id,
            knowledge_base_id="personal",
            status="ready",
        ).all()
    ]
    return search_knowledge_bases(["personal"], data.query, data.top_k, source_ids)
