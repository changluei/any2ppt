from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.ai.editor_agent import AgentAction, EditorToolbox, run_editor_react_agent
from app.ai.exceptions import AIError
from app.ai.llm_client import DeepSeekClient
from app.ai.vector_store import ProjectVectorStore
from app.models import EditorAgentMessage, LessonArtifact, Project, ProjectImage
from app.services.artifact_service import (
    add_slide_image,
    artifact_out,
    remove_slide_image,
    revise_artifact,
    rewrite_slide_from_agent,
)
from app.services.knowledge_base_service import search_knowledge_bases


def message_out(message: EditorAgentMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "project_id": message.project_id,
        "role": message.role,
        "content": message.content,
        "image_id": message.image_id,
        "image_name": message.image_name,
        "artifact_version_no": message.artifact_version_no,
        "created_at": message.created_at,
    }


def list_editor_messages(db: Session, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        db.query(EditorAgentMessage)
        .filter(EditorAgentMessage.project_id == project_id)
        .order_by(EditorAgentMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return [message_out(item) for item in reversed(rows)]


class ProjectEditorToolbox(EditorToolbox):
    def __init__(
        self,
        db: Session,
        project: Project,
        artifact: LessonArtifact,
        *,
        attachment: ProjectImage | None,
    ):
        self.db = db
        self.project = project
        self.artifact = artifact
        self.attachment = attachment
        self.store = ProjectVectorStore()
        self.inspected_deck = False
        self.inspected_slides: set[str] = set()
        self.retrieved_citations: list[dict[str, Any]] = []
        self.executed_mutations: list[str] = []
        self.latest_artifact = artifact_out(artifact, artifact.versions[-1])

    def close(self) -> None:
        self.store.close()

    def _current(self) -> dict[str, Any]:
        return self.artifact.versions[-1].content

    def _slide(self, arguments: dict[str, Any]) -> dict[str, Any]:
        slides = self._current().get("slides", [])
        slide_id = str(arguments.get("slide_id") or "").strip()
        raw_order = arguments.get("order")
        try:
            order = int(raw_order) if raw_order not in (None, "") else 0
        except (TypeError, ValueError):
            order = 0
        slide = next(
            (
                item for item in slides
                if (slide_id and item.get("slide_id") == slide_id)
                or (order and item.get("order") == order)
            ),
            None,
        )
        if not slide:
            raise ValueError("未找到目标页面，请先 inspect_deck 获取真实页码和 slide_id")
        return slide

    def _inspect_slide(self, slide: dict[str, Any]) -> dict[str, Any]:
        slides = self._current().get("slides", [])
        index = slides.index(slide)
        self.inspected_slides.add(slide["slide_id"])
        return {
            "slide": slide,
            "previous": (
                {"order": slides[index - 1]["order"], "title": slides[index - 1]["title"]}
                if index > 0
                else None
            ),
            "next": (
                {"order": slides[index + 1]["order"], "title": slides[index + 1]["title"]}
                if index + 1 < len(slides)
                else None
            ),
        }

    def _validate(self, slide: dict[str, Any]) -> dict[str, Any]:
        content = self._current()
        layouts = content.get("theme_layouts", []) or ["default"]
        issues: list[str] = []
        layout = slide.get("layout", "default")
        if layout not in layouts:
            issues.append(f"布局 {layout} 不属于当前模板")
        capability = next(
            (
                item for item in content.get("theme_layout_capabilities", [])
                if item.get("name") == layout
            ),
            None,
        )
        for slot in (capability or {}).get("slots", []):
            if slot != "default" and f"::{slot}::" not in slide.get("markdown", ""):
                issues.append(f"缺少布局插槽 ::{slot}::")
        markdown = slide.get("markdown", "")
        nonempty_lines = [line for line in markdown.splitlines() if line.strip()]
        if len(markdown) > 800 or len(nonempty_lines) > 14:
            issues.append("页面文字偏密，建议精简或拆页")
        if not any(line.startswith("# ") for line in nonempty_lines):
            issues.append("页面缺少一级标题")
        image_ids = [item.get("image_id") for item in slide.get("images", [])]
        if len(image_ids) != len(set(image_ids)):
            issues.append("页面存在重复图片")
        return {
            "slide_id": slide.get("slide_id"),
            "order": slide.get("order"),
            "valid": not issues,
            "issues": issues,
            "version_no": self.artifact.current_version_no,
        }

    def execute(self, action: AgentAction, arguments: dict[str, Any]) -> dict[str, Any]:
        content = self._current()
        if action == "inspect_deck":
            self.inspected_deck = True
            return {
                "version_no": self.artifact.current_version_no,
                "title": content.get("deck_title") or content.get("title"),
                "theme": {
                    "id": content.get("theme_id"),
                    "name": content.get("theme_name"),
                    "layouts": content.get("theme_layouts", []),
                    "layout_capabilities": content.get("theme_layout_capabilities", []),
                    "design_guidance": content.get("theme_design_guidance", ""),
                    "image_strategy": content.get("theme_image_strategy", ""),
                },
                "slides": [
                    {
                        "slide_id": item.get("slide_id"),
                        "order": item.get("order"),
                        "title": item.get("title"),
                        "layout": item.get("layout"),
                        "image_count": len(item.get("images", [])),
                    }
                    for item in content.get("slides", [])
                ],
            }

        if action == "inspect_slide":
            return self._inspect_slide(self._slide(arguments))

        if action == "search_knowledge":
            query = str(arguments.get("query") or "").strip()
            if not query:
                raise ValueError("search_knowledge 缺少 query")
            try:
                top_k = max(1, min(6, int(arguments.get("top_k", 4))))
            except (TypeError, ValueError):
                top_k = 4
            library_ids = list(self.project.knowledge_base_ids or [])
            if not library_ids:
                return {
                    "query": query,
                    "results": [],
                    "warning": "当前项目没有勾选知识库，不能执行 RAG 检索。",
                }
            rows = search_knowledge_bases(
                library_ids,
                query,
                top_k=top_k,
                store=self.store,
                min_score=0.0,
            )
            for row in rows:
                citation = {
                    "source_id": row["source_id"],
                    "chunk_id": row["chunk_id"],
                    "filename": row["filename"],
                    "location": row["location"],
                    "quote": row["content"][:600],
                    "score": row.get("score"),
                }
                key = (citation["source_id"], citation["chunk_id"])
                if not any(
                    (item["source_id"], item["chunk_id"]) == key
                    for item in self.retrieved_citations
                ):
                    self.retrieved_citations.append(citation)
            return {
                "query": query,
                "results": [
                    {
                        "content": row["content"][:1000],
                        "filename": row["filename"],
                        "location": row["location"],
                        "score": row.get("score"),
                        "knowledge_base_id": row.get("knowledge_base_id"),
                    }
                    for row in rows
                ],
            }

        if action == "rewrite_slide":
            slide = self._slide(arguments)
            if slide["slide_id"] not in self.inspected_slides:
                raise ValueError("rewrite_slide 前必须先 inspect_slide")
            markdown = str(arguments.get("markdown") or "").strip()
            if not markdown:
                raise ValueError("rewrite_slide 缺少完整 markdown")
            self.latest_artifact = rewrite_slide_from_agent(
                self.db,
                self.artifact,
                self.artifact.current_version_no,
                slide["slide_id"],
                markdown,
                title=str(arguments.get("title") or ""),
                layout=str(arguments.get("layout") or ""),
                citations=self.retrieved_citations,
            )
            self.executed_mutations.append("rewrite_slide")
            return {
                "changed": True,
                "slide_id": slide["slide_id"],
                "version_no": self.latest_artifact["version_no"],
                "next": "调用 inspect_slide 和 validate_slide 检查新版本",
            }

        if action == "place_image":
            if not self.attachment:
                raise ValueError("本轮消息没有可放置的附件图片")
            slide = self._slide(arguments)
            if slide["slide_id"] not in self.inspected_slides:
                raise ValueError("place_image 前必须先 inspect_slide")
            if any(
                item.get("image_id") == self.attachment.id
                for item in slide.get("images", [])
            ):
                raise ValueError("附件图片已经位于该页面，不能重复添加")
            position = str(arguments.get("position") or "right")
            self.latest_artifact = add_slide_image(
                self.db,
                self.artifact,
                self.artifact.current_version_no,
                slide["slide_id"],
                self.attachment,
                position,
                str(arguments.get("caption") or ""),
            )
            self.executed_mutations.append("place_image")
            return {
                "changed": True,
                "slide_id": slide["slide_id"],
                "position": position,
                "version_no": self.latest_artifact["version_no"],
                "vision_notice": "仅依据用户描述、文件名和尺寸放置，未分析图片像素。",
            }

        if action == "remove_image":
            placement_id = str(arguments.get("placement_id") or "").strip()
            if not placement_id:
                raise ValueError("remove_image 缺少 placement_id")
            self.latest_artifact = remove_slide_image(
                self.db,
                self.artifact,
                self.artifact.current_version_no,
                placement_id,
            )
            self.executed_mutations.append("remove_image")
            return {
                "changed": True,
                "placement_id": placement_id,
                "version_no": self.latest_artifact["version_no"],
            }

        if action == "validate_slide":
            return self._validate(self._slide(arguments))

        raise ValueError(f"不支持的 Agent 工具：{action}")


def _target_slide(content: dict[str, Any], message: str, current_slide_id: str) -> dict[str, Any]:
    order_match = re.search(r"第\s*(\d+)\s*(?:页|张)", message)
    order = int(order_match.group(1)) if order_match else 0
    return next(
        (
            item for item in content.get("slides", [])
            if (order and item.get("order") == order)
            or (not order and item.get("slide_id") == current_slide_id)
        ),
        content.get("slides", [None])[0],
    )


def _fallback_position(message: str) -> str:
    if re.search(r"背景|铺满", message):
        return "background"
    if re.search(r"左侧|左边", message):
        return "left"
    if re.search(r"居中|中央|中间", message):
        return "center"
    if re.search(r"宽图|横幅|底部|下方", message):
        return "wide"
    return "right"


def _fallback_chat(
    db: Session,
    artifact: LessonArtifact,
    message: str,
    current_slide_id: str,
    attachment: ProjectImage | None,
) -> tuple[str, dict[str, Any], list[str]]:
    content = artifact.versions[-1].content
    target = _target_slide(content, message, current_slide_id)
    if not target:
        raise ValueError("课件中没有可编辑页面")
    actions: list[str] = []
    latest = artifact_out(artifact, artifact.versions[-1])
    if attachment:
        latest = add_slide_image(
            db,
            artifact,
            artifact.current_version_no,
            target["slide_id"],
            attachment,
            _fallback_position(message),
            "",
        )
        actions.append("place_image")
    is_greeting = bool(re.fullmatch(r"(你好|您好|在吗|谢谢|谢谢你)[？?！!。,\s]*", message))
    image_only = bool(
        attachment
        and re.search(r"添加|放到|放在|放进|放入|插入|使用|这张|图片", message)
        and not re.search(r"精简|扩写|重写|改写|调整文字|修改标题|补充内容|改成", message)
    )
    if message and not is_greeting and not image_only:
        latest = revise_artifact(
            db,
            artifact,
            artifact.current_version_no,
            "slide",
            target["slide_id"],
            message,
            True,
        )
        actions.append("rewrite_slide")
    response = (
        f"已完成第 {target['order']} 页的修改。当前模型不可用，因此本次采用了受限规则模式，请检查结果。"
        if actions
        else "你好！你可以告诉我需要查看或修改哪一页。"
    )
    return response, latest, actions


def run_editor_chat(
    db: Session,
    project: Project,
    *,
    message: str,
    current_slide_id: str,
    base_version_no: int,
    image_id: str | None,
) -> dict[str, Any]:
    artifact = (
        db.query(LessonArtifact)
        .filter_by(project_id=project.id, type="slide_deck")
        .with_for_update()
        .first()
    )
    if not artifact or not artifact.versions:
        raise ValueError("当前项目还没有可编辑课件")
    if artifact.current_version_no != base_version_no:
        raise RuntimeError(f"VERSION_CONFLICT:{artifact.current_version_no}")
    if not any(
        item.get("slide_id") == current_slide_id
        for item in artifact.versions[-1].content.get("slides", [])
    ):
        raise ValueError("当前页面不存在")

    attachment = db.get(ProjectImage, image_id) if image_id else None
    if image_id and (not attachment or attachment.project_id != project.id):
        raise ValueError("附件图片不存在或不属于当前项目")

    clean_message = message.strip() or "请把本次附带的图片合理放到当前页面，不修改页面文字。"
    previous_rows = (
        db.query(EditorAgentMessage)
        .filter(EditorAgentMessage.project_id == project.id)
        .order_by(EditorAgentMessage.created_at.desc())
        .limit(12)
        .all()
    )
    history = [
        {"role": item.role, "content": item.content, "image_name": item.image_name}
        for item in reversed(previous_rows)
    ]
    user_row = EditorAgentMessage(
        project_id=project.id,
        role="user",
        content=clean_message,
        image_id=attachment.id if attachment else None,
        image_name=attachment.original_name if attachment else None,
        tool_trace=[],
        artifact_version_no=artifact.current_version_no,
    )
    db.add(user_row)
    db.commit()

    client = DeepSeekClient()
    trace_id = str(uuid.uuid4())
    degraded = False
    actions: list[str]
    latest: dict[str, Any] | None
    if client.configured:
        toolbox = ProjectEditorToolbox(db, project, artifact, attachment=attachment)
        try:
            try:
                result = run_editor_react_agent(
                    user_message=clean_message,
                    current_slide_id=current_slide_id,
                    project_context={
                        "project_id": project.id,
                        "subject": project.subject,
                        "grade": project.grade,
                        "lesson_topic": project.lesson_topic,
                        "knowledge_base_ids": project.knowledge_base_ids,
                        "image_vision_available": False,
                    },
                    history=history,
                    attachment=(
                        {
                            "image_id": attachment.id,
                            "filename": attachment.original_name,
                            "width": attachment.width,
                            "height": attachment.height,
                            "vision_available": False,
                        }
                        if attachment
                        else None
                    ),
                    tools=toolbox,
                    llm=client,
                    trace_id=trace_id,
                )
                response = result.response
                actions = result.actions
                trace_id = result.trace_id
                latest = toolbox.latest_artifact if any(
                    action in {"rewrite_slide", "place_image", "remove_image"}
                    for action in actions
                ) else None
                trace = [
                    {
                        "action": item.get("action"),
                        "ok": bool(item.get("ok")),
                        "error": item.get("error"),
                    }
                    for item in result.observations
                ]
            except AIError:
                degraded = True
                if toolbox.executed_mutations:
                    actions = list(toolbox.executed_mutations)
                    latest = toolbox.latest_artifact
                    response = (
                        "已保存模型中断前完成的修改。后续检查暂时未完成，请先查看当前版本，"
                        "确认后再继续提出下一步要求。"
                    )
                    trace = [
                        {"action": action, "ok": True, "degraded": True}
                        for action in actions
                    ] + [{"action": "model_interrupted", "ok": False}]
                else:
                    response, fallback_artifact, actions = _fallback_chat(
                        db,
                        artifact,
                        clean_message,
                        current_slide_id,
                        attachment,
                    )
                    latest = fallback_artifact if actions else None
                    trace = [{"action": action, "ok": True, "degraded": True} for action in actions]
        finally:
            toolbox.close()
    else:
        degraded = True
        response, fallback_artifact, actions = _fallback_chat(
            db,
            artifact,
            clean_message,
            current_slide_id,
            attachment,
        )
        latest = fallback_artifact if actions else None
        trace = [{"action": action, "ok": True, "degraded": True} for action in actions]

    assistant_row = EditorAgentMessage(
        project_id=project.id,
        role="assistant",
        content=response,
        trace_id=trace_id,
        tool_trace=trace,
        artifact_version_no=artifact.current_version_no,
    )
    db.add(assistant_row)
    db.commit()
    db.refresh(assistant_row)
    return {
        "message": message_out(assistant_row),
        "artifact": latest,
        "actions": actions,
        "trace_id": trace_id,
        "degraded": degraded,
    }
