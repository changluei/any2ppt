"""语文、数学、英语官方知识库与个人知识库 API。

官方库由离线脚本导入且只读；用户上传始终进入 personal，并可被多个项目
重复选择。多库检索会在 service 层合并和排序证据。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import KnowledgeBase, Project, SourceDocument
from app.schemas.api import KnowledgeBaseOut, SearchRequest, SearchResult, SourceOut
from app.services.knowledge_base_service import (
    ensure_knowledge_bases,
    search_knowledge_bases,
    validate_knowledge_base_ids,
)
from app.services.source_service import delete_source, index_source, save_upload


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


def personal_source_or_404(db: Session, source_id: str) -> SourceDocument:
    """取得个人库资料，并阻止通过该 API 修改官方资料。"""
    source = db.query(SourceDocument).filter_by(
        id=source_id,
        knowledge_base_id="personal",
    ).first()
    if not source:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_FOUND", "message": "个人资料不存在"})
    return source


@router.get("", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases(db: Session = Depends(get_db)):
    """列出固定知识库及文档、chunk 和体积统计。"""
    return ensure_knowledge_bases(db)


@router.post("/search", response_model=list[SearchResult])
def search(data: SearchRequest, db: Session = Depends(get_db)):
    """对所选知识库执行跨库向量检索。"""
    ensure_knowledge_bases(db)
    library_ids = validate_knowledge_base_ids(db, data.knowledge_base_ids or ["personal"])
    return search_knowledge_bases(
        library_ids,
        data.query,
        data.top_k,
        data.source_ids,
    )


@router.get("/{knowledge_base_id}/sources", response_model=list[SourceOut])
def list_sources(knowledge_base_id: str, db: Session = Depends(get_db)):
    """列出某知识库的原始资料元数据。"""
    ensure_knowledge_bases(db)
    if not db.get(KnowledgeBase, knowledge_base_id):
        raise HTTPException(404, detail={"code": "KNOWLEDGE_BASE_NOT_FOUND", "message": "知识库不存在"})
    return db.query(SourceDocument).filter_by(
        knowledge_base_id=knowledge_base_id,
    ).order_by(SourceDocument.created_at.desc()).all()


@router.post("/personal/sources", response_model=SourceOut, status_code=201)
async def upload_personal_source(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """保存用户文件到个人库，并在后台解析、切片、向量化。"""
    if project_id and not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    try:
        source = save_upload(
            db,
            project_id,
            file.filename or "unnamed",
            file.content_type or "",
            await file.read(),
        )
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_SOURCE_FILE", "message": str(exc)}) from exc
    if source.status != "ready":
        background.add_task(index_source, source.id)
    return source


@router.get("/personal/sources/{source_id}", response_model=SourceOut)
def get_personal_source(source_id: str, db: Session = Depends(get_db)):
    """读取一份个人资料的索引状态与错误信息。"""
    return personal_source_or_404(db, source_id)


@router.post("/personal/sources/{source_id}/index", response_model=SourceOut)
def retry_personal_source(source_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    """重新排队失败的个人资料索引任务。"""
    source = personal_source_or_404(db, source_id)
    source.status = "uploaded"
    source.error_message = None
    db.commit()
    db.refresh(source)
    background.add_task(index_source, source.id)
    return source


@router.delete("/personal/sources/{source_id}", status_code=204)
def remove_personal_source(source_id: str, db: Session = Depends(get_db)):
    """同时删除个人资料文件、MySQL 元数据和 Chroma chunks。"""
    source = personal_source_or_404(db, source_id)
    try:
        delete_source(db, source)
    except RuntimeError as exc:
        raise HTTPException(
            503,
            detail={"code": str(exc), "message": "资料删除未完成，已记录可重试错误"},
        ) from exc
