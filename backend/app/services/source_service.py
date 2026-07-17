import hashlib
import re
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from app.ai.ingestion import parse_document, split_blocks
from app.ai.vector_store import ProjectVectorStore
from app.core.config import get_settings
from app.models import SourceDocument


ALLOWED = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain", ".md": "text/markdown"}


def safe_filename(name: str) -> str:
    value = Path(name).name
    value = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", value)
    if not value or value in {".", ".."}:
        raise ValueError("文件名无效")
    return value[:200]


def save_upload(db: Session, project_id: str, filename: str, content_type: str, data: bytes) -> SourceDocument:
    settings = get_settings()
    clean = safe_filename(filename)
    suffix = Path(clean).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("仅支持 PDF、DOCX、TXT、Markdown")
    if not data:
        raise ValueError("不能上传空文件")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"文件不能超过 {settings.max_upload_mb}MB")
    digest = hashlib.sha256(data).hexdigest()
    exists = db.query(SourceDocument).filter_by(project_id=project_id, sha256=digest).first()
    if exists:
        raise ValueError("同一项目中已存在相同文件")
    project_dir = settings.upload_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{suffix}"
    path = project_dir / stored
    path.write_bytes(data)
    source = SourceDocument(project_id=project_id, original_name=clean, stored_name=stored, media_type=content_type or ALLOWED[suffix], size=len(data), sha256=digest, storage_path=str(path), status="uploaded")
    try:
        db.add(source); db.commit(); db.refresh(source)
    except Exception:
        db.rollback(); path.unlink(missing_ok=True); raise
    return source


def index_source(source_id: str) -> None:
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        source = db.get(SourceDocument, source_id)
        if not source:
            return
        source.status = "parsing"; db.commit()
        blocks = parse_document(Path(source.storage_path))
        source.status = "indexing"; db.commit()
        chunks = split_blocks(blocks, source.id)
        ProjectVectorStore().add_documents(source.project_id, source.id, source.original_name, chunks)
        source.status = "ready"; source.error_message = None; db.commit()
    except Exception as exc:
        source = db.get(SourceDocument, source_id)
        if source:
            source.status = "failed"; source.error_message = str(exc)[:500]; db.commit()
    finally:
        db.close()


def delete_source(db: Session, source: SourceDocument) -> None:
    ProjectVectorStore().delete_by_source(source.project_id, source.id)
    Path(source.storage_path).unlink(missing_ok=True)
    db.delete(source); db.commit()

