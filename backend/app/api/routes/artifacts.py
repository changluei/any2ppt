from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import LessonArtifact, ArtifactVersion, ProjectImage
from app.schemas.api import ArtifactOut, RevisionRequest, SlideImagePlacementCreate, SlideMarkdownUpdate
from app.services.artifact_service import (
    add_slide_image,
    artifact_out,
    remove_slide_image,
    revise_artifact,
    save_version,
    update_slide_markdown,
)

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}", response_model=ArtifactOut)
def get_artifact(artifact_id: str, version: Optional[int] = None, db: Session = Depends(get_db)):
    artifact = db.get(LessonArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    item = next((v for v in artifact.versions if v.version_no == version), None) if version else artifact.versions[-1]
    if not item:
        raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": "版本不存在"})
    return artifact_out(artifact, item)


@router.get("/{artifact_id}/versions", response_model=list[ArtifactOut])
def versions(artifact_id: str, db: Session = Depends(get_db)):
    artifact = db.get(LessonArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    return [artifact_out(artifact, version) for version in reversed(artifact.versions)]


@router.post("/{artifact_id}/revise", response_model=ArtifactOut)
def revise(artifact_id: str, data: RevisionRequest, db: Session = Depends(get_db)):
    artifact = db.get(LessonArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    try: return revise_artifact(db, artifact, data.base_version_no, data.target_type, data.target_id, data.instruction, data.sync_related)
    except RuntimeError as exc:
        if str(exc).startswith("VERSION_CONFLICT"):
            raise HTTPException(
                409,
                detail={"code": "VERSION_CONFLICT", "message": "版本冲突", "current_version": artifact.current_version_no},
            ) from exc
        raise
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_REVISION", "message": str(exc)}) from exc


@router.post("/{artifact_id}/markdown", response_model=ArtifactOut)
def save_markdown(artifact_id: str, data: SlideMarkdownUpdate, db: Session = Depends(get_db)):
    artifact = db.get(LessonArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    try:
        return update_slide_markdown(
            db,
            artifact,
            data.base_version_no,
            data.slide_id,
            data.markdown,
        )
    except RuntimeError as exc:
        if str(exc).startswith("VERSION_CONFLICT"):
            raise HTTPException(
                409,
                detail={"code": "VERSION_CONFLICT", "message": "课件已被更新，请刷新后重试", "current_version": artifact.current_version_no},
            ) from exc
        raise
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_MARKDOWN_UPDATE", "message": str(exc)}) from exc


@router.post("/{artifact_id}/images", response_model=ArtifactOut)
def place_image(artifact_id: str, data: SlideImagePlacementCreate, db: Session = Depends(get_db)):
    artifact = db.get(LessonArtifact, artifact_id)
    image = db.get(ProjectImage, data.image_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    if not image:
        raise HTTPException(404, detail={"code": "IMAGE_NOT_FOUND", "message": "图片不存在"})
    try:
        return add_slide_image(
            db,
            artifact,
            data.base_version_no,
            data.slide_id,
            image,
            data.position,
            data.caption,
        )
    except RuntimeError as exc:
        if str(exc).startswith("VERSION_CONFLICT"):
            raise HTTPException(
                409,
                detail={"code": "VERSION_CONFLICT", "message": "课件已被更新，请刷新后重试", "current_version": artifact.current_version_no},
            ) from exc
        raise
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_IMAGE_PLACEMENT", "message": str(exc)}) from exc


@router.delete("/{artifact_id}/images/{placement_id}", response_model=ArtifactOut)
def unplace_image(
    artifact_id: str,
    placement_id: str,
    base_version_no: int,
    db: Session = Depends(get_db),
):
    artifact = db.get(LessonArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    try:
        return remove_slide_image(db, artifact, base_version_no, placement_id)
    except RuntimeError as exc:
        if str(exc).startswith("VERSION_CONFLICT"):
            raise HTTPException(
                409,
                detail={"code": "VERSION_CONFLICT", "message": "课件已被更新，请刷新后重试", "current_version": artifact.current_version_no},
            ) from exc
        raise
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_IMAGE_PLACEMENT", "message": str(exc)}) from exc


@router.post("/{artifact_id}/rollback/{version_no}", response_model=ArtifactOut)
def rollback(artifact_id: str, version_no: int, db: Session = Depends(get_db)):
    artifact = db.get(LessonArtifact, artifact_id)
    if not artifact:
        raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "产物不存在"})
    old = next((v for v in artifact.versions if v.version_no == version_no), None)
    if not old:
        raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": "版本不存在"})
    save_version(db, artifact.project_id, artifact.type, old.content, old.citations, old.warnings, "rollback", [])
    db.commit()
    db.refresh(artifact)
    return artifact_out(artifact, artifact.versions[-1])
