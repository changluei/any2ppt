from __future__ import annotations

import html
import json
import shutil
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import ArtifactVersion, ExportJob, LessonArtifact


EXPORT_REQUIRED_TYPES = {
    "teacher": {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"},
    "student": {"slide_deck", "exercise_set"},
}


def _load_versions(db: Session, job: ExportJob) -> dict[str, ArtifactVersion]:
    selected_ids = list((job.selected_versions or {}).values())
    if selected_ids:
        versions = (
            db.query(ArtifactVersion)
            .join(LessonArtifact, ArtifactVersion.artifact_id == LessonArtifact.id)
            .filter(
                LessonArtifact.project_id == job.project_id,
                ArtifactVersion.id.in_(selected_ids),
            )
            .all()
        )
    else:
        artifacts = db.query(LessonArtifact).filter_by(project_id=job.project_id).all()
        versions = [artifact.versions[-1] for artifact in artifacts if artifact.versions]

    by_type = {version.artifact.type: version for version in versions}
    required = EXPORT_REQUIRED_TYPES[job.package_type]
    missing = sorted(required - by_type.keys())
    if missing:
        raise ValueError(f"EXPORT_ARTIFACTS_MISSING: {', '.join(missing)}")
    return {artifact_type: by_type[artifact_type] for artifact_type in sorted(required)}


def _write_slides(output: Path, slide_deck: dict) -> None:
    slides = slide_deck.get("slides", [])
    (output / "slides.md").write_text(
        "\n\n---\n\n".join(slide.get("markdown", "") for slide in slides),
        "utf-8",
    )
    sections = "".join(
        "<section>"
        f"<h1>{html.escape(slide.get('title', ''))}</h1>"
        f"<pre>{html.escape(slide.get('markdown', ''))}</pre>"
        "</section>"
        for slide in slides
    )
    page = (
        "<!doctype html><meta charset='utf-8'><title>LessonDeck</title>"
        "<style>"
        "body{font-family:sans-serif;background:#eef2f8;margin:0}"
        "section{box-sizing:border-box;width:100vw;height:100vh;"
        "padding:8vh 10vw;background:white;border-bottom:1px solid #ccd3df}"
        "h1{font-size:5vw}"
        "pre{font:2vw/1.6 sans-serif;white-space:pre-wrap}"
        "@media print{section{page-break-after:always}}"
        "</style>"
        f"{sections}"
    )
    (output / "slides.html").write_text(page, "utf-8")


def create_export(job_id: str) -> None:
    db = SessionLocal()
    job = db.get(ExportJob, job_id)
    if not job:
        db.close()
        return

    root = get_settings().export_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "_tmp" / job.id
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=False)

    try:
        job.status = "running"
        db.commit()

        versions = _load_versions(db, job)
        latest = {artifact_type: version.content for artifact_type, version in versions.items()}

        output = tmp / "package"
        output.mkdir()
        (output / "README.txt").write_text(
            "LessonDeck 备课导出包\n内容由教师最终确认后使用。",
            "utf-8",
        )

        if "slide_deck" in latest:
            _write_slides(output, latest["slide_deck"])

        if job.package_type == "teacher":
            names = {
                "lesson_plan": "教学设计.json",
                "speaker_notes": "逐页讲稿.json",
                "exercise_set": "教师版练习.json",
            }
            for artifact_type, filename in names.items():
                (output / filename).write_text(
                    json.dumps(latest[artifact_type], ensure_ascii=False, indent=2),
                    "utf-8",
                )
            citations = [version.citations for version in versions.values() if version.citations]
            (output / "引用清单.json").write_text(
                json.dumps(citations, ensure_ascii=False, indent=2),
                "utf-8",
            )
        else:
            student = json.loads(json.dumps(latest["exercise_set"], ensure_ascii=False))
            for item in student.get("exercises", []):
                item.pop("answer", None)
                item.pop("explanation", None)
            (output / "学生练习.json").write_text(
                json.dumps(student, ensure_ascii=False, indent=2),
                "utf-8",
            )

        zip_path = root / f"{job.project_id}_{job.package_type}_{job.id}.zip"
        tmp_zip = tmp / zip_path.name
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in output.iterdir():
                archive.write(file, file.name)
        tmp_zip.replace(zip_path)

        job.selected_versions = {artifact_type: version.id for artifact_type, version in versions.items()}
        job.file_path = str(zip_path)
        job.status = "succeeded"
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)[:500]
        db.commit()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        db.close()
