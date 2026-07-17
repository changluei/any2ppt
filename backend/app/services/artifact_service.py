from datetime import datetime
from sqlalchemy.orm import Session
from app.ai.generation import generate_lesson_bundle, revise_block
from app.ai.schemas import LessonContext
from app.ai.graph import review_artifacts, initial_node_state
from app.core.database import SessionLocal
from app.models import Project, AITask, LessonArtifact, ArtifactVersion, GraphRun


ARTIFACT_TYPES = ("lesson_plan", "slide_deck", "speaker_notes", "exercise_set")


def artifact_out(artifact: LessonArtifact, version: ArtifactVersion) -> dict:
    return {"artifact_id": artifact.id, "version_id": version.id, "project_id": artifact.project_id, "type": artifact.type, "version_no": version.version_no, "content": version.content, "citations": version.citations or [], "warnings": version.warnings or [], "created_at": version.created_at}


def save_version(db: Session, project_id: str, artifact_type: str, content: dict, citations: list, warnings: list, change_type="generated", changed_ids=None) -> LessonArtifact:
    artifact = db.query(LessonArtifact).filter_by(project_id=project_id, type=artifact_type).with_for_update().first()
    if not artifact:
        artifact = LessonArtifact(project_id=project_id, type=artifact_type); db.add(artifact); db.flush()
    parent = artifact.versions[-1] if artifact.versions else None
    version_no = artifact.current_version_no + 1
    version = ArtifactVersion(version_no=version_no, parent_version_id=parent.id if parent else None, change_type=change_type, changed_ids=changed_ids or [], content=content, citations=citations, warnings=warnings)
    artifact.versions.append(version); artifact.current_version_no = version_no; db.flush()
    return artifact


def run_generation_task(task_id: str) -> None:
    db = SessionLocal()
    task = db.get(AITask, task_id)
    if not task or task.status == "cancelled":
        db.close(); return
    try:
        task.status = "running"; task.stage = "资料检索"; task.progress = 15; task.started_at = datetime.utcnow(); db.commit()
        project = db.get(Project, task.project_id)
        context = LessonContext(project_id=project.id, subject=project.subject, grade=project.grade, textbook_version=project.textbook_version, lesson_topic=project.lesson_topic, lesson_count=project.lesson_count, student_profile=project.student_profile, selected_source_ids=task.input_snapshot.get("selected_source_ids", []), teacher_requirements=task.input_snapshot.get("teacher_requirements") or project.teacher_requirements)
        task.stage = "模型生成"; task.progress = 45; db.commit()
        bundle = generate_lesson_bundle(context)
        if db.get(AITask, task_id).status == "cancelled":
            db.close(); return
        task.stage = "结构校验与保存"; task.progress = 80; db.commit()
        first = None
        citation_rows = [c.model_dump() for c in bundle.citations]
        for artifact_type in ARTIFACT_TYPES:
            artifact = save_version(db, project.id, artifact_type, bundle.artifacts[artifact_type], citation_rows, bundle.warnings)
            first = first or artifact.id
        task.status = "succeeded"; task.stage = "已完成（降级草案）" if bundle.degraded else "已完成"; task.progress = 100; task.result_artifact_id = first; task.finished_at = datetime.utcnow()
        graph = GraphRun(project_id=project.id, task_id=task.id, status="awaiting_confirmation", current_node="human_confirm", nodes=initial_node_state(), issues=review_artifacts(bundle.artifacts), state_snapshot={"degraded": bundle.degraded, "model": bundle.model})
        for node in graph.nodes:
            if node["node_id"] == "human_confirm": node["status"] = "running"
            elif node["node_id"] != "finalize": node["status"] = "succeeded"
        db.add(graph); db.commit()
    except Exception as exc:
        db.rollback(); task = db.get(AITask, task_id)
        if task:
            task.status = "failed"; task.stage = "生成失败"; task.error_code = getattr(exc, "code", "INTERNAL_ERROR"); task.error_message = str(exc)[:500]; task.finished_at = datetime.utcnow(); db.commit()
    finally:
        db.close()


def revise_artifact(db: Session, artifact: LessonArtifact, base_version_no: int, target_type: str, target_id: str, instruction: str, sync_related: bool = False) -> dict:
    if artifact.current_version_no != base_version_no:
        raise RuntimeError(f"VERSION_CONFLICT:{artifact.current_version_no}")
    current = artifact.versions[-1]
    content, changed_ids = revise_block(current.content, target_type, target_id, instruction)
    save_version(db, artifact.project_id, artifact.type, content, current.citations, current.warnings, "local_revision", changed_ids)
    if sync_related and artifact.type == "slide_deck" and target_type == "slide":
        notes = db.query(LessonArtifact).filter_by(project_id=artifact.project_id, type="speaker_notes").with_for_update().first()
        if notes and notes.versions:
            note_current = notes.versions[-1]
            note_content, note_ids = revise_block(note_current.content, "note", target_id, f"同步课件修改：{instruction}")
            save_version(db, artifact.project_id, notes.type, note_content, note_current.citations, note_current.warnings, "synced_revision", note_ids)
    db.commit(); db.refresh(artifact)
    return artifact_out(artifact, artifact.versions[-1])
