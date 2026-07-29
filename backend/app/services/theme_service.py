"""Slidev 主题目录、能力解析、选择、下载缓存与项目绑定。

首页读取目录不会下载包；用户选中主题后才调用 renderer 安装并缓存。
capabilities 会进入生成 prompt，避免 AI 只使用 default 布局。
"""

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
    """读取静态主题目录；缓存避免每次请求重复读盘。"""
    return json.loads(CATALOG_PATH.read_text("utf-8"))


def public_themes() -> list[dict[str, Any]]:
    """返回可安全暴露给首页的主题列表。"""
    return [
        {key: value for key, value in item.items() if key != "match_terms"}
        for item in theme_catalog()
    ]


def get_theme(theme_id: str) -> dict[str, Any] | None:
    """按主题稳定 ID 查目录项。"""
    return next((item for item in theme_catalog() if item["id"] == theme_id), None)


def _layout_usage(name: str) -> str:
    """为常见 layout 生成中文语义用途，供 LLM 选择布局。"""
    if any(token in name for token in ("cover", "intro", "lead")):
        return "封面、开场或章节引入；使用短标题和一句核心信息"
    if "section" in name:
        return "章节过渡；只呈现章节名和简短提示"
    if "quote" in name:
        return "引用、核心观点或关键原文"
    if any(token in name for token in ("two-cols", "columns", "compare")):
        return "比较、左右对应关系、概念与案例或问题与结论"
    if any(token in name for token in ("four", "grid", "cell", "panel", "item")):
        return "并列要点、分类或评价维度"
    if any(token in name for token in ("image", "figure", "showcase", "full")):
        return "大图、图表、案例截图或沉浸式视觉页面"
    if any(token in name for token in ("steps", "timeline", "diagram")):
        return "流程、阶段、时间发展或概念关系"
    if any(token in name for token in ("fact", "statement", "bigtype")):
        return "单个关键数字、结论或强强调观点"
    return "常规正文页"


def _fallback_capabilities(theme: dict[str, Any]) -> dict[str, Any]:
    """renderer 不可用时从目录 layouts 构造保守能力描述。"""
    return {
        "schema_version": 2,
        "theme_spec": f"{theme['package']}@{theme['version']}",
        "package_name": theme["package"],
        "layouts": [
            {
                "name": name,
                "slots": ["left", "right"] if name in {"two-cols", "columns", "compare"} else ["default"],
                "props": [],
                "usage": _layout_usage(name),
                "markdown_pattern": (
                    "::left::\n{{left}}\n\n::right::\n{{right}}"
                    if name in {"two-cols", "columns", "compare"}
                    else "# {{title}}\n\n{{body}}"
                ),
                "supports_images": any(token in name for token in ("image", "figure", "showcase", "full")),
                "structural": name != "default",
            }
            for name in theme.get("layouts", ["default"])
        ],
        "components": [],
        "source": "catalog-fallback",
    }


@lru_cache(maxsize=32)
def get_theme_capabilities(theme_id: str) -> dict[str, Any]:
    """优先读取 renderer 解析结果，失败则返回 fallback。"""
    theme = get_theme(theme_id)
    if not theme:
        raise ValueError("THEME_NOT_FOUND")
    settings = get_settings()
    fallback = _fallback_capabilities(theme)
    if not settings.slidev_renderer_url:
        return fallback
    try:
        response = httpx.post(
            f"{settings.slidev_renderer_url.rstrip('/')}/capabilities",
            json={
                "theme_package": theme["package"],
                "theme_version": theme["version"],
            },
            timeout=settings.slidev_renderer_timeout_seconds,
        )
        response.raise_for_status()
        manifest = response.json()
        layouts = [
            row for row in manifest.get("layouts", [])
            if isinstance(row, dict) and row.get("name")
        ]
        if not layouts:
            return fallback
        manifest["layouts"] = layouts
        manifest["source"] = "installed-theme"
        return manifest
    except (httpx.HTTPError, ValueError, TypeError):
        return fallback


def select_theme(context: LessonContext, preferred_theme_id: str | None = None) -> dict[str, Any]:
    """尊重用户显式选择，否则按课程关键词做确定性推荐。"""
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
    """请求 renderer 下载或复用缓存，并保存项目能力快照。"""
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
    get_theme_capabilities.cache_clear()


def delete_project_theme(project_id: str) -> None:
    """只删项目绑定快照，不删供其他项目复用的全局主题缓存。"""
    settings = get_settings()
    root = settings.theme_cache_dir.resolve()
    target = (root / project_id).resolve()
    if target.parent == root:
        shutil.rmtree(target, ignore_errors=True)
