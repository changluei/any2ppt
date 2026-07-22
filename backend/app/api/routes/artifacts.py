from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import LessonArtifact, ArtifactVersion
from app.schemas.api import ArtifactOut, RevisionRequest
from app.services.artifact_service import artifact_out, revise_artifact, save_version

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
