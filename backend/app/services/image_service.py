from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ProjectImage
from app.services.source_service import safe_filename


ALLOWED_IMAGES = {
    ".png": {"image/png", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".webp": {"image/webp", "application/octet-stream"},
}
CANONICAL_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def image_out(image: ProjectImage) -> dict:
    return {
        "id": image.id,
        "project_id": image.project_id,
        "original_name": image.original_name,
        "media_type": image.media_type,
        "size": image.size,
        "width": image.width,
        "height": image.height,
        "content_url": f"/api/images/{image.id}/content",
        "created_at": image.created_at,
    }


def save_image(
    db: Session,
    project_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> ProjectImage:
    settings = get_settings()
    clean = safe_filename(filename)
    suffix = Path(clean).suffix.lower()
    if suffix not in ALLOWED_IMAGES:
        raise ValueError("仅支持 PNG、JPG、JPEG、WEBP 图片")
    if not data:
        raise ValueError("不能上传空图片")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"图片不能超过 {settings.max_upload_mb}MB")
    if content_type and content_type not in ALLOWED_IMAGES[suffix]:
        raise ValueError("图片类型与扩展名不匹配")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("图片内容无效或已损坏") from exc
    if width < 32 or height < 32:
        raise ValueError("图片尺寸至少为 32×32")
    if width * height > 40_000_000:
        raise ValueError("图片像素尺寸过大")

    digest = hashlib.sha256(data).hexdigest()
    if db.query(ProjectImage).filter_by(project_id=project_id, sha256=digest).first():
        raise ValueError("同一项目中已存在相同图片")
    project_dir = settings.upload_dir / project_id / "images"
    project_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{suffix}"
    path = project_dir / stored
    path.write_bytes(data)
    record = ProjectImage(
        project_id=project_id,
        original_name=clean,
        stored_name=stored,
        media_type=CANONICAL_MEDIA[suffix],
        size=len(data),
        sha256=digest,
        storage_path=str(path),
        width=width,
        height=height,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return record
