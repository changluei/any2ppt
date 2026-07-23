import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.generation import generate_lesson_bundle, revise_block
from app.ai.graph import initial_node_state, review_quality
from app.ai.schemas import LessonContext, SkillRequest
from app.ai.skills import run_skill
from app.core.database import SessionLocal
from app.models import AITask, ArtifactVersion, GraphRun, LessonArtifact, Project


ARTIFACT_TYPES = ("lesson_plan", "slide_deck", "speaker_notes", "exercise_set")


def artifact_out(artifact: LessonArtifact, version: ArtifactVersion) -> dict:
    parent = next((item for item in artifact.versions if item.id == version.parent_version_id), None)
    previous_hashes = _block_hashes(parent.content) if parent else {}
    current_hashes = _block_hashes(version.content)
    unchanged_hashes = [
        {"id": block_id, "sha256": digest}
        for block_id, digest in current_hashes.items()
        if previous_hashes.get(block_id) == digest
    ]
    return {
        "artifact_id": artifact.id,
        "version_id": version.id,
        "project_id": artifact.project_id,
        "type": artifact.type,
        "version_no": version.version_no,
        "parent_version_id": version.parent_version_id,
        "change_type": version.change_type,
        "changed_ids": version.changed_ids or [],
        "unchanged_hashes": unchanged_hashes,
        "content": version.content,
        "citations": version.citations or [],
        "warnings": version.warnings or [],
        "created_at": version.created_at,
    }


def _block_hashes(content: dict) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for collection in ("objectives", "stages", "assessments", "slides", "notes", "exercises"):
        for index, row in enumerate(content.get(collection, []) or []):
            block_id = (
                row.get("id")
                or row.get("slide_id")
                or row.get("exercise_id")
                or f"{collection}:{index}"
            )
            encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            hashes[str(block_id)] = hashlib.sha256(encoded).hexdigest()
    return hashes


def validate_artifact_content(artifact_type: str, content: dict) -> None:
    required_collection = {
        "lesson_plan": "stages",
        "slide_deck": "slides",
        "speaker_notes": "notes",
        "exercise_set": "exercises",
    }[artifact_type]
    rows = content.get(required_collection)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{artifact_type} 缺少有效的 {required_collection}")
    id_field = {
        "stages": "id",
        "slides": "slide_id",
        "notes": "slide_id",
        "exercises": "exercise_id",
    }[required_collection]
    ids = [row.get(id_field) for row in rows]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{required_collection} 的稳定 ID 缺失或重复")


def save_version(db: Session, project_id: str, artifact_type: str, content: dict, citations: list, warnings: list, change_type="generated", changed_ids=None) -> LessonArtifact:
    validate_artifact_content(artifact_type, content)
    artifact = db.query(LessonArtifact).filter_by(project_id=project_id, type=artifact_type).with_for_update().first()
    if not artifact:
        artifact = LessonArtifact(project_id=project_id, type=artifact_type)
        db.add(artifact)
        db.flush()
    parent = artifact.versions[-1] if artifact.versions else None
    version_no = artifact.current_version_no + 1
    version = ArtifactVersion(
        version_no=version_no,
        parent_version_id=parent.id if parent else None,
        change_type=change_type,
        changed_ids=changed_ids or [],
        content=content,
        citations=citations,
        warnings=warnings,
    )
    artifact.versions.append(version)
    artifact.current_version_no = version_no
    db.flush()
    return artifact


def run_generation_task(task_id: str) -> None:
    db = SessionLocal()
    task = db.get(AITask, task_id)
    if not task or task.status == "cancelled":
        db.close()
        return
    if task.type == "full_lesson":
        db.close()
        from app.services.graph_service import start_task_graph

        start_task_graph(task_id)
        return
    try:
        task.status = "running"
        task.stage = "资料检索"
        task.progress = 15
        task.started_at = datetime.utcnow()
        db.commit()
        project = db.get(Project, task.project_id)
        if not project:
            task.status = "failed"
            task.error_code = "PROJECT_NOT_FOUND"
            task.error_message = "项目不存在"
            task.finished_at = datetime.utcnow()
            db.commit()
            return
        context = LessonContext(project_id=project.id, subject=project.subject, grade=project.grade, textbook_version=project.textbook_version, lesson_topic=project.lesson_topic, lesson_count=project.lesson_count, student_profile=project.student_profile, selected_source_ids=task.input_snapshot.get("selected_source_ids", []), teacher_requirements=task.input_snapshot.get("teacher_requirements") or project.teacher_requirements)
        task.stage = "模型生成"
        task.progress = 45
        db.commit()
        if task.type != "full_lesson":
            response = run_skill(
                task.type,
                SkillRequest(context=context, instruction=context.teacher_requirements),
                trace_id=task.trace_id,
            )
            task.status = "succeeded"
            task.stage = "已完成（降级草案）" if response.degraded else "已完成"
            task.progress = 100
            task.result_snapshot = response.model_dump(mode="json")
            task.finished_at = datetime.utcnow()
            db.commit()
            return
        bundle = generate_lesson_bundle(context, trace_id=task.trace_id)
        if db.get(AITask, task_id).status == "cancelled":
            db.close()
            return
        task.stage = "结构校验与保存"
        task.progress = 80
        db.commit()
        first = None
        citation_rows = [c.model_dump() for c in bundle.citations]
        for artifact_type in ARTIFACT_TYPES:
            artifact = save_version(db, project.id, artifact_type, bundle.artifacts[artifact_type], citation_rows, bundle.warnings)
            first = first or artifact.id
        task.status = "succeeded"
        task.stage = "已完成（降级草案）" if bundle.degraded else "已完成"
        task.progress = 100
        task.result_artifact_id = first
        task.result_snapshot = {
            "kind": "full_lesson",
            "artifact_types": list(ARTIFACT_TYPES),
            "model": bundle.model,
            "degraded": bundle.degraded,
            "trace": bundle.trace.model_dump(mode="json") if bundle.trace else None,
        }
        task.finished_at = datetime.utcnow()
        graph = GraphRun(
            project_id=project.id,
            task_id=task.id,
            thread_id=task.trace_id,
            checkpoint_ref=f"task:{task.id}",
            status="running",
            current_node="analyze_sources",
            nodes=initial_node_state(),
            issues=[],
            state_snapshot={
                "degraded": bundle.degraded,
                "model": bundle.model,
                "citations": [c.model_dump() for c in bundle.citations],
                "trace": bundle.trace.model_dump(mode="json") if bundle.trace else None,
            },
        )
        db.add(graph)
        db.commit()
        from app.services.graph_service import execute_graph_run

        execute_graph_run(graph.id)
    except Exception as exc:
        db.rollback()
        task = db.get(AITask, task_id)
        if task:
            task.status = "failed"
            task.stage = "生成失败"
            task.error_code = getattr(exc, "code", "INTERNAL_ERROR")
            task.error_message = str(exc)[:500]
            task.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def revise_artifact(db: Session, artifact: LessonArtifact, base_version_no: int, target_type: str, target_id: str, instruction: str, sync_related: bool = False) -> dict:
    if artifact.current_version_no != base_version_no:
        raise RuntimeError(f"VERSION_CONFLICT:{artifact.current_version_no}")
    current = artifact.versions[-1]
    content, changed_ids = revise_block(current.content, target_type, target_id, instruction, citations=current.citations)
    before_hashes = _block_hashes(current.content)
    after_hashes = _block_hashes(content)
    actually_changed = sorted(
        block_id for block_id in set(before_hashes) | set(after_hashes)
        if before_hashes.get(block_id) != after_hashes.get(block_id)
    )
    if actually_changed != sorted(changed_ids):
        raise ValueError("局部修改越过了目标块边界")
    save_version(db, artifact.project_id, artifact.type, content, current.citations, current.warnings, "local_revision", changed_ids)
    if sync_related and artifact.type == "slide_deck" and target_type == "slide":
        notes = db.query(LessonArtifact).filter_by(project_id=artifact.project_id, type="speaker_notes").with_for_update().first()
        if notes and notes.versions:
            note_current = notes.versions[-1]
            note_content, note_ids = revise_block(note_current.content, "note", target_id, f"同步课件修改：{instruction}", citations=note_current.citations)
            save_version(db, artifact.project_id, notes.type, note_content, note_current.citations, note_current.warnings, "synced_revision", note_ids)
    db.commit()
    db.refresh(artifact)
    return artifact_out(artifact, artifact.versions[-1])
