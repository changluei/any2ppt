from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Project
from app.schemas.api import (
    EditorAgentChatOut,
    EditorAgentChatRequest,
    EditorAgentMessageOut,
)
from app.services.editor_agent_service import list_editor_messages, run_editor_chat


router = APIRouter(prefix="/api/projects", tags=["editor-agent"])


@router.get(
    "/{project_id}/agent/messages",
    response_model=list[EditorAgentMessageOut],
)
def messages(project_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(
            404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        )
    return list_editor_messages(db, project_id)


@router.post(
    "/{project_id}/agent/chat",
    response_model=EditorAgentChatOut,
)
def chat(
    project_id: str,
    data: EditorAgentChatRequest,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        )
    try:
        return run_editor_chat(
            db,
            project,
            message=data.message,
            current_slide_id=data.current_slide_id,
            base_version_no=data.base_version_no,
            image_id=data.image_id,
        )
    except RuntimeError as exc:
        if str(exc).startswith("VERSION_CONFLICT"):
            current = str(exc).partition(":")[2]
            raise HTTPException(
                409,
                detail={
                    "code": "VERSION_CONFLICT",
                    "message": "课件已被更新，请刷新到最新版本后重试",
                    "current_version": int(current),
                },
            ) from exc
        raise
    except ValueError as exc:
        raise HTTPException(
            400,
            detail={"code": "INVALID_AGENT_REQUEST", "message": str(exc)},
        ) from exc
