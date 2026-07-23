from __future__ import annotations

import json
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.ai.schemas import LessonContext
from app.core.config import get_settings


CATALOG_PATH = Path(__file__).resolve().parents[1] / "theme_catalog.json"


@lru_cache(maxsize=1)
def theme_catalog() -> list[dict[str, Any]]:
    return json.loads(CATALOG_PATH.read_text("utf-8"))


def public_themes() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "match_terms"}
        for item in theme_catalog()
    ]


def get_theme(theme_id: str) -> dict[str, Any] | None:
    return next((item for item in theme_catalog() if item["id"] == theme_id), None)


def select_theme(context: LessonContext, preferred_theme_id: str | None = None) -> dict[str, Any]:
    if preferred_theme_id and (preferred := get_theme(preferred_theme_id)):
        result = {key: value for key, value in preferred.items() if key != "match_terms"}
        result["match_reason"] = "创建项目时已选择此模板"
        return result
    text = " ".join(
        [
            context.subject,
            context.grade,
            context.lesson_topic,
            context.student_profile,
            context.teacher_requirements,
        ]
    ).lower()
    ranked: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for index, item in enumerate(theme_catalog()):
        matches = [term for term in item["match_terms"] if term.lower() in text]
        explicit = (
            item["name"].lower() in text
            or item["id"].lower() in text
            or item["package"].lower() in text
        )
        score = len(matches) + (20 if explicit else 0)
        ranked.append((score, -index, item, matches))
    score, _, selected, matches = max(ranked, key=lambda row: (row[0], row[1]))
    if score == 0:
        selected = theme_catalog()[0]
    result = {key: value for key, value in selected.items() if key != "match_terms"}
    result["match_reason"] = (
        f"匹配到：{'、'.join(matches[:4])}"
        if matches
        else "未指定风格，使用清晰通用主题"
    )
    return result


def prepare_project_theme(project_id: str, theme_id: str) -> None:
    theme = get_theme(theme_id)
    if not theme:
        raise ValueError("THEME_NOT_FOUND")
    settings = get_settings()
    if not settings.slidev_renderer_url:
        return
    response = httpx.post(
        f"{settings.slidev_renderer_url.rstrip('/')}/prepare",
        json={
            "project_id": project_id,
            "theme_package": theme["package"],
            "theme_version": theme["version"],
        },
        timeout=settings.slidev_renderer_timeout_seconds,
    )
    response.raise_for_status()


def delete_project_theme(project_id: str) -> None:
    settings = get_settings()
    root = settings.theme_cache_dir.resolve()
    target = (root / project_id).resolve()
    if target.parent == root:
        shutil.rmtree(target, ignore_errors=True)
