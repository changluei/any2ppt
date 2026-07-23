import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.generation import generate_lesson_bundle, revise_block
from app.ai.graph import initial_node_state, review_quality
from app.ai.schemas import LessonContext, SkillRequest
from app.ai.skills import run_skill
from app.core.database import SessionLocal
from app.models import AITask, ArtifactVersion, GraphRun, LessonArtifact, Project, ProjectImage
from app.services.theme_service import select_theme


ARTIFACT_TYPES = ("lesson_plan", "slide_deck", "speaker_notes", "exercise_set")


def compose_ppt_artifact(artifacts: dict[str, dict], theme: dict | None = None) -> dict:
    """Fold every teacher-facing deliverable into one slide-deck contract."""
    deck = deepcopy(artifacts["slide_deck"])
    plan = artifacts["lesson_plan"]
    note_rows = artifacts["speaker_notes"].get("notes", [])
    notes = {
        item["slide_id"]: item
        for item in note_rows
    }
    exercises = artifacts["exercise_set"].get("exercises", [])
    slides = deck.get("slides", [])
    theme_layouts = (theme or {}).get("layouts", ["default"])
    default_layout = "default" if "default" in theme_layouts else theme_layouts[0]

    def slide_at(order: int) -> dict | None:
        return next((item for item in slides if item.get("order") == order), None)

    objectives = plan.get("objectives", [])
    target = slide_at(4)
    if target:
        target["markdown"] = "# 本课学习目标\n\n" + "\n".join(
            f"- {item.get('behavior', '')}（{item.get('criterion', '完成课堂任务')}）"
            for item in objectives
        )

    target = slide_at(9)
    if target:
        key_points = "；".join(plan.get("key_points", [])) or "围绕课题形成核心理解"
        difficult = "；".join(plan.get("difficult_points", [])) or "把所学迁移到新情境"
        target["markdown"] = f"# 学习要点\n\n**重点：** {key_points}\n\n**难点：** {difficult}"

    for order, level in ((11, "基础"), (12, "巩固"), (13, "提高")):
        target = slide_at(order)
        items = [item for item in exercises if item.get("level") == level]
        if target and items:
            blocks = []
            for index, item in enumerate(items, 1):
                blocks.append(
                    f"## {level}题 {index}\n\n{item.get('question', '')}"
                    f"\n\n**参考答案：** {item.get('answer', '')}"
                    f"\n\n**解析：** {item.get('explanation', '')}"
                )
            target["markdown"] = f"# {level}练习\n\n" + "\n\n".join(blocks)

    stages = plan.get("stages", [])
    if len(slides) < 18:
        slides.append({
            "slide_id": f"SLIDE-{len(slides) + 1:02d}",
            "order": len(slides) + 1,
            "title": "教学流程",
            "layout": "steps" if "steps" in theme_layouts else default_layout,
            "markdown": "# 教学流程\n\n" + "\n".join(
                f"- {item.get('name', '')} · {item.get('time_minutes', 0)} 分钟：{item.get('student_actions', '')}"
                for item in stages
            ),
            "teaching_stage": stages[0].get("id", "STAGE-1") if stages else "STAGE-1",
            "objective_ids": [item.get("id") for item in objectives if item.get("id")],
            "citations": [],
        })
    assessments = plan.get("assessments", [])
    if len(slides) < 18:
        slides.append({
            "slide_id": f"SLIDE-{len(slides) + 1:02d}",
            "order": len(slides) + 1,
            "title": "课堂评价",
            "layout": "panels" if "panels" in theme_layouts else ("fact" if "fact" in theme_layouts else default_layout),
            "markdown": "# 课堂评价\n\n" + "\n".join(
                f"- {item.get('method', '')}：{item.get('success_criteria', '')}"
                for item in assessments
            ),
            "teaching_stage": stages[-1].get("id", "STAGE-4") if stages else "STAGE-4",
            "objective_ids": [item.get("id") for item in objectives if item.get("id")],
            "citations": [],
        })

    for slide in slides:
        if slide.get("slide_id") not in notes:
            note = {
                "slide_id": slide.get("slide_id"),
                "explanation": f"结合“{slide.get('title', '')}”组织学生表达，并根据回答追问理由。",
                "questions": [f"关于“{slide.get('title', '')}”，你能说出哪些发现？"],
                "expected_answers": ["学生结合本页信息说明自己的发现和依据。"],
                "transition": "接下来进入下一个学习任务。",
                "board_notes": slide.get("title", ""),
                "estimated_minutes": 2,
            }
            note_rows.append(note)
            notes[slide.get("slide_id")] = note
        slide["speaker_note"] = notes.get(slide.get("slide_id"), {})
    deck["slides"] = slides
    deck["contains_full_lesson"] = True
    if theme:
        deck["theme"] = theme["package"]
        deck["theme_id"] = theme["id"]
        deck["theme_name"] = theme["name"]
        deck["theme_version"] = theme["version"]
        deck["theme_description"] = theme["description"]
        deck["theme_match_reason"] = theme["match_reason"]
        deck["theme_palette"] = theme["palette"]
        deck["theme_preview_url"] = theme["preview_url"]
        deck["theme_source_url"] = theme["source_url"]
        deck["theme_layouts"] = theme["layouts"]
        deck["theme_design_guidance"] = theme["design_guidance"]
        deck["theme_image_strategy"] = theme["image_strategy"]
        deck["theme_density"] = theme["density"]
        deck["theme_config"] = theme["theme_config"]
    return deck


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
        selected_theme = select_theme(
            LessonContext(
                project_id=project.id,
                subject=project.subject,
                grade=project.grade,
                lesson_topic=project.lesson_topic,
                student_profile=project.student_profile,
                teacher_requirements=task.input_snapshot.get("teacher_requirements") or project.teacher_requirements,
            ),
            project.theme_id,
        )
        context = LessonContext(
            project_id=project.id,
            subject=project.subject,
            grade=project.grade,
            textbook_version=project.textbook_version,
            lesson_topic=project.lesson_topic,
            lesson_count=project.lesson_count,
            student_profile=project.student_profile,
            selected_source_ids=task.input_snapshot.get("selected_source_ids", []),
            teacher_requirements=task.input_snapshot.get("teacher_requirements") or project.teacher_requirements,
            theme_id=selected_theme["id"],
            theme_name=selected_theme["name"],
            theme_description=selected_theme["description"],
            theme_layouts=selected_theme["layouts"],
            theme_guidance=selected_theme["design_guidance"],
            theme_image_strategy=selected_theme["image_strategy"],
        )
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
        bundle.artifacts["slide_deck"] = compose_ppt_artifact(
            bundle.artifacts,
            selected_theme,
        )
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


def update_slide_markdown(
    db: Session,
    artifact: LessonArtifact,
    base_version_no: int,
    slide_id: str,
    markdown: str,
) -> dict:
    """Persist a teacher's direct Markdown edit as an immutable deck version."""
    if artifact.type != "slide_deck":
        raise ValueError("只有课件支持 Markdown 源码编辑")
    if artifact.current_version_no != base_version_no:
        raise RuntimeError(f"VERSION_CONFLICT:{artifact.current_version_no}")

    current = artifact.versions[-1]
    content = deepcopy(current.content)
    target = next(
        (item for item in content.get("slides", []) if item.get("slide_id") == slide_id),
        None,
    )
    if not target:
        raise ValueError("未找到需要修改的课件页")

    normalized = markdown.strip()
    if target.get("markdown", "").strip() == normalized:
        return artifact_out(artifact, current)
    target["markdown"] = normalized
    heading = next(
        (
            line.removeprefix("# ").strip()
            for line in normalized.splitlines()
            if line.startswith("# ") and line.removeprefix("# ").strip()
        ),
        None,
    )
    if heading:
        target["title"] = heading[:160]

    save_version(
        db,
        artifact.project_id,
        artifact.type,
        content,
        current.citations,
        current.warnings,
        "manual_markdown",
        [slide_id],
    )
    db.commit()
    db.refresh(artifact)
    return artifact_out(artifact, artifact.versions[-1])


IMAGE_PLACEMENT_PRESETS = {
    "left": {"x": 4, "y": 18, "width": 40, "height": 66, "opacity": 1},
    "right": {"x": 56, "y": 18, "width": 40, "height": 66, "opacity": 1},
    "center": {"x": 25, "y": 16, "width": 50, "height": 70, "opacity": 1},
    "wide": {"x": 10, "y": 34, "width": 80, "height": 54, "opacity": 1},
    "background": {"x": 0, "y": 0, "width": 100, "height": 100, "opacity": 0.3},
}


def add_slide_image(
    db: Session,
    artifact: LessonArtifact,
    base_version_no: int,
    slide_id: str,
    image: ProjectImage,
    position: str,
    caption: str,
) -> dict:
    if artifact.type != "slide_deck":
        raise ValueError("只有课件支持添加图片")
    if artifact.project_id != image.project_id:
        raise ValueError("图片不属于当前备课项目")
    if artifact.current_version_no != base_version_no:
        raise RuntimeError(f"VERSION_CONFLICT:{artifact.current_version_no}")
    if position not in IMAGE_PLACEMENT_PRESETS:
        raise ValueError("图片位置无效")

    current = artifact.versions[-1]
    content = deepcopy(current.content)
    target = next(
        (item for item in content.get("slides", []) if item.get("slide_id") == slide_id),
        None,
    )
    if not target:
        raise ValueError("未找到需要添加图片的课件页")
    placement = {
        "placement_id": str(uuid.uuid4()),
        "image_id": image.id,
        "original_name": image.original_name,
        "position": position,
        "caption": caption.strip(),
        **IMAGE_PLACEMENT_PRESETS[position],
    }
    target.setdefault("images", []).append(placement)
    save_version(
        db,
        artifact.project_id,
        artifact.type,
        content,
        current.citations,
        current.warnings,
        "image_placement",
        [slide_id],
    )
    db.commit()
    db.refresh(artifact)
    return artifact_out(artifact, artifact.versions[-1])


def remove_slide_image(
    db: Session,
    artifact: LessonArtifact,
    base_version_no: int,
    placement_id: str,
) -> dict:
    if artifact.type != "slide_deck":
        raise ValueError("只有课件支持移除图片")
    if artifact.current_version_no != base_version_no:
        raise RuntimeError(f"VERSION_CONFLICT:{artifact.current_version_no}")
    current = artifact.versions[-1]
    content = deepcopy(current.content)
    changed_slide_id = None
    for slide in content.get("slides", []):
        placements = slide.get("images", [])
        kept = [item for item in placements if item.get("placement_id") != placement_id]
        if len(kept) != len(placements):
            slide["images"] = kept
            changed_slide_id = slide.get("slide_id")
            break
    if not changed_slide_id:
        raise ValueError("未找到需要移除的图片")
    save_version(
        db,
        artifact.project_id,
        artifact.type,
        content,
        current.citations,
        current.warnings,
        "image_placement",
        [changed_slide_id],
    )
    db.commit()
    db.refresh(artifact)
    return artifact_out(artifact, artifact.versions[-1])
