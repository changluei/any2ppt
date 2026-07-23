from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Project, ProjectImage
from app.schemas.api import ProjectImageOut
from app.services.image_service import image_out, save_image


router = APIRouter(tags=["images"])


@router.post(
    "/api/projects/{project_id}/images",
    response_model=ProjectImageOut,
    status_code=201,
)
async def upload_image(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    try:
        image = save_image(
            db,
            project_id,
            file.filename or "image.png",
            file.content_type or "",
            await file.read(),
        )
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_IMAGE_FILE", "message": str(exc)}) from exc
    return image_out(image)


@router.get("/api/projects/{project_id}/images", response_model=list[ProjectImageOut])
def list_images(project_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"})
    rows = (
        db.query(ProjectImage)
        .filter_by(project_id=project_id)
        .order_by(ProjectImage.created_at.desc())
        .all()
    )
    return [image_out(row) for row in rows]


@router.get("/api/images/{image_id}/content")
def image_content(image_id: str, db: Session = Depends(get_db)):
    image = db.get(ProjectImage, image_id)
    if not image:
        raise HTTPException(404, detail={"code": "IMAGE_NOT_FOUND", "message": "图片不存在"})
    path = Path(image.storage_path)
    if not path.is_file():
        raise HTTPException(404, detail={"code": "IMAGE_FILE_MISSING", "message": "图片文件不存在"})
    return FileResponse(path, media_type=image.media_type, filename=image.original_name)
