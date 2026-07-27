import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.ingestion import parse_document, split_blocks
from app.ai.vector_store import ProjectVectorStore
from app.core.config import get_settings
from app.models import SourceDocument
from app.services.knowledge_base_service import ensure_knowledge_bases


ALLOWED = {
    ".pdf": ("application/pdf", "application/octet-stream"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"),
    ".txt": ("text/plain", "text/plain; charset=utf-8", "application/octet-stream"),
    ".md": ("text/markdown", "text/x-markdown", "text/markdown; charset=utf-8", "application/octet-stream"),
}


def safe_filename(name: str) -> str:
    value = Path(name).name
    value = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", value)
    if not value or value in {".", ".."}:
        raise ValueError("文件名无效")
    return value[:200]


def save_upload(
    db: Session,
    project_id: str | None,
    filename: str,
    content_type: str,
    data: bytes,
) -> SourceDocument:
    settings = get_settings()
    clean = safe_filename(filename)
    suffix = Path(clean).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("仅支持 PDF、DOCX、TXT、Markdown")
    if not data:
        raise ValueError("不能上传空文件")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"文件不能超过 {settings.max_upload_mb}MB")
    if content_type and content_type not in ALLOWED[suffix]:
        raise ValueError("文件类型与扩展名不匹配")
    digest = hashlib.sha256(data).hexdigest()
    ensure_knowledge_bases(db)
    exists = db.query(SourceDocument).filter_by(knowledge_base_id="personal", sha256=digest).first()
    if exists:
        return exists
    library_dir = settings.upload_dir / "personal"
    library_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{suffix}"
    path = library_dir / stored
    path.write_bytes(data)
    source = SourceDocument(
        project_id=project_id,
        knowledge_base_id="personal",
        original_name=clean,
        stored_name=stored,
        media_type=content_type or ALLOWED[suffix][0],
        size=len(data),
        sha256=digest,
        storage_path=str(path),
        status="uploaded",
    )
    try:
        db.add(source)
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return source


def index_source(source_id: str) -> None:
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        source = db.get(SourceDocument, source_id)
        if not source:
            return
        source.status = "parsing"
        db.commit()
        blocks = parse_document(Path(source.storage_path))
        source.status = "indexing"
        db.commit()
        settings = get_settings()
        chunks = split_blocks(blocks, source.id, settings.ai_chunk_size, settings.ai_chunk_overlap)
        ProjectVectorStore().add_documents("personal", source.id, source.original_name, chunks)
        source.status = "ready"
        source.error_message = None
        db.commit()
        ensure_knowledge_bases(db)
    except Exception as exc:
        db.rollback()
        source = db.get(SourceDocument, source_id)
        if source:
            source.status = "failed"
            source.error_message = str(exc)[:500]
            db.commit()
    finally:
        db.close()


def migrate_legacy_personal_indexes() -> int:
    """Copy ready project-era documents into the durable personal namespace once."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    store = ProjectVectorStore()
    try:
        source_ids = [
            row[0]
            for row in db.query(SourceDocument.id).filter_by(
                knowledge_base_id="personal",
                status="ready",
            ).all()
            if store.count("personal", row[0]) == 0
        ]
    finally:
        store.close()
        db.close()
    for source_id in source_ids:
        index_source(source_id)
    return len(source_ids)


def delete_source(db: Session, source: SourceDocument) -> None:
    try:
        ProjectVectorStore().delete_by_source(source.knowledge_base_id, source.id)
    except Exception as exc:
        source.status = "failed"
        source.error_message = f"向量删除失败：{exc}"[:500]
        db.commit()
        raise RuntimeError("VECTOR_DELETE_FAILED") from exc
    try:
        Path(source.storage_path).unlink(missing_ok=True)
    except OSError as exc:
        source.status = "failed"
        source.error_message = f"文件删除失败：{exc}"[:500]
        db.commit()
        raise RuntimeError("FILE_DELETE_FAILED") from exc
    db.delete(source)
    db.commit()
    ensure_knowledge_bases(db)
