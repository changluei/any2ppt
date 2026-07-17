import json
import re
import shutil
import tempfile
import zipfile
import html
from pathlib import Path
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import ExportJob, LessonArtifact


def create_export(job_id: str) -> None:
    db = SessionLocal(); job = db.get(ExportJob, job_id)
    if not job: db.close(); return
    tmp = Path(tempfile.mkdtemp(prefix="lessondeck_"))
    try:
        job.status = "running"; db.commit()
        artifacts = db.query(LessonArtifact).filter_by(project_id=job.project_id).all()
        latest = {a.type: a.versions[-1].content for a in artifacts if a.versions}
        output = tmp / "package"; output.mkdir()
        (output / "README.txt").write_text("LessonDeck 备课导出包\n内容由教师最终确认后使用。", "utf-8")
        if "slide_deck" in latest:
            slides = latest["slide_deck"].get("slides", [])
            (output / "slides.md").write_text("\n\n---\n\n".join(s.get("markdown", "") for s in slides), "utf-8")
            sections = "".join(f"<section><h1>{html.escape(s.get('title',''))}</h1><pre>{html.escape(s.get('markdown',''))}</pre></section>" for s in slides)
            page = f"<!doctype html><meta charset='utf-8'><title>LessonDeck</title><style>body{{font-family:sans-serif;background:#eef2f8;margin:0}}section{{box-sizing:border-box;width:100vw;height:100vh;padding:8vh 10vw;background:white;border-bottom:1px solid #ccd3df}}h1{{font-size:5vw}}pre{{font:2vw/1.6 sans-serif;white-space:pre-wrap}}@media print{{section{{page-break-after:always}}}}</style>{sections}"
            (output / "slides.html").write_text(page, "utf-8")
        if job.package_type == "teacher":
            names = {"lesson_plan": "教学设计.json", "speaker_notes": "逐页讲稿.json", "exercise_set": "教师版练习.json"}
            for key, name in names.items():
                if key in latest: (output / name).write_text(json.dumps(latest[key], ensure_ascii=False, indent=2), "utf-8")
            citations = [v.citations for a in artifacts for v in a.versions[-1:] if v.citations]
            (output / "引用清单.json").write_text(json.dumps(citations, ensure_ascii=False, indent=2), "utf-8")
        elif "exercise_set" in latest:
            student = json.loads(json.dumps(latest["exercise_set"], ensure_ascii=False))
            for item in student.get("exercises", []):
                item.pop("answer", None); item.pop("explanation", None)
            (output / "学生练习.json").write_text(json.dumps(student, ensure_ascii=False, indent=2), "utf-8")
        root = get_settings().export_dir; root.mkdir(parents=True, exist_ok=True)
        zip_path = root / f"{job.project_id}_{job.package_type}_{job.id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in output.iterdir(): archive.write(file, file.name)
        job.file_path = str(zip_path); job.status = "succeeded"; db.commit()
    except Exception as exc:
        job.status = "failed"; job.error_message = str(exc)[:500]; db.commit()
    finally:
        shutil.rmtree(tmp, ignore_errors=True); db.close()
