"""单页 Slidev 预览的主题装配、请求去重与 PNG 缓存。

同一“版本 + 主题”使用锁合并并发渲染；renderer 生成的 PNG 按制品版本落盘，
后续请求直接命中缓存。实时编辑的 iframe 预览由前端 SlidevPreview 负责。
"""

from __future__ import annotations

import shutil
import threading
import uuid
from copy import deepcopy
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ArtifactVersion, LessonArtifact, Project, ProjectImage
from app.services.export_service import _prepare_slidev_job
from app.services.theme_service import get_theme, get_theme_capabilities


_preview_locks: dict[str, threading.Lock] = {}
_preview_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    """为相同预览键复用互斥锁，避免重复启动 Slidev。"""
    with _preview_locks_guard:
        return _preview_locks.setdefault(key, threading.Lock())


def _themed_deck(project: Project, content: dict) -> tuple[dict, dict]:
    """把项目主题能力合并进课件副本，同时返回主题配置。"""
    theme = get_theme(project.theme_id)
    if not theme:
        raise ValueError("项目选择的主题不存在")
    capabilities = get_theme_capabilities(theme["id"])
    layout_capabilities = capabilities.get("layouts", [])
    layouts = [item["name"] for item in layout_capabilities if item.get("name")] or theme["layouts"]
    default_layout = "default" if "default" in layouts else layouts[0]
    deck = deepcopy(content)
    for slide in deck.get("slides", []):
        if slide.get("layout") not in layouts:
            slide["layout"] = default_layout
    deck.update(
        {
            "theme": theme["package"],
            "theme_id": theme["id"],
            "theme_name": theme["name"],
            "theme_version": theme["version"],
            "theme_config": theme["theme_config"],
            "theme_palette": theme["palette"],
            "theme_layouts": layouts,
            "theme_layout_capabilities": layout_capabilities,
        }
    )
    return deck, theme


def render_slide_preview(
    db: Session,
    artifact: LessonArtifact,
    slide_id: str,
    version_no: int | None = None,
) -> Path:
    """返回指定版本/页面的缓存 PNG；未命中时调用 renderer 生成。"""
    if artifact.type != "slide_deck":
        raise ValueError("只有课件支持主题预览")
    version: ArtifactVersion | None = (
        next((item for item in artifact.versions if item.version_no == version_no), None)
        if version_no
        else artifact.versions[-1]
    )
    if not version:
        raise ValueError("课件版本不存在")
    project = db.get(Project, artifact.project_id)
    if not project:
        raise ValueError("项目不存在")
    deck, theme = _themed_deck(project, version.content)
    slides = deck.get("slides", [])
    selected = next((item for item in slides if item.get("slide_id") == slide_id), None)
    if not selected:
        raise ValueError("课件页面不存在")

    settings = get_settings()
    if not settings.slidev_renderer_url:
        raise ValueError("Slidev 渲染服务未配置")
    cache_dir = (
        settings.export_dir.resolve().parent
        / "previews"
        / str(version.id)
        / theme["id"]
    )
    selected_path = cache_dir / f"{int(selected.get('order', 1))}.png"
    if selected_path.is_file():
        return selected_path

    cache_key = f"{version.id}:{theme['id']}"
    with _lock_for(cache_key):
        if selected_path.is_file():
            return selected_path
        job_id = str(uuid.uuid4())
        job_dir = settings.export_dir.resolve().parent / "render_jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        try:
            image_ids = {
                placement.get("image_id")
                for slide in slides
                for placement in slide.get("images", [])
                if placement.get("image_id")
            }
            image_records = {
                image.id: image
                for image in db.query(ProjectImage).filter(ProjectImage.id.in_(image_ids)).all()
            } if image_ids else {}
            _prepare_slidev_job(job_dir, deck, image_records)
            response = httpx.post(
                f"{settings.slidev_renderer_url.rstrip('/')}/preview",
                json={
                    "job_id": job_id,
                    "project_id": project.id,
                    "theme_package": theme["package"],
                    "theme_version": theme["version"],
                    "slide_order": int(selected.get("order", 1)),
                },
                timeout=settings.slidev_renderer_timeout_seconds,
            )
            response.raise_for_status()
            rendered = job_dir / "preview"
            cache_dir.mkdir(parents=True, exist_ok=True)
            source = rendered / f"{int(selected.get('order', 1))}.png"
            if source.is_file():
                shutil.copy2(source, selected_path)
            if not selected_path.is_file():
                raise RuntimeError("SLIDEV_PREVIEW_OUTPUT_MISSING")
            return selected_path
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)
