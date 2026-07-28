from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .llm_client import DeepSeekClient


AgentAction = Literal[
    "inspect_deck",
    "inspect_slide",
    "search_knowledge",
    "rewrite_slide",
    "place_image",
    "remove_image",
    "validate_slide",
    "finish",
]

MUTATING_ACTIONS = {"rewrite_slide", "place_image", "remove_image"}
MAX_AGENT_STEPS = 7
MAX_MUTATIONS = 3


class ReActDecision(BaseModel):
    action: AgentAction
    arguments: dict[str, Any] = Field(default_factory=dict)
    response: str = Field(
        default="",
        description="Only set when action is finish. This is the concise user-facing Chinese reply.",
    )


class EditorToolbox(Protocol):
    def execute(self, action: AgentAction, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class EditorAgentResult:
    response: str
    trace_id: str
    actions: list[str] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""


SYSTEM_PROMPT = """
你是 Any2PPT 编辑页的 ReAct Agent。你不能看见图片像素；附件只提供文件名、宽高和用户文字描述，
绝不能声称识别了图片内容。

你必须在“选择一个工具 → 读取 observation → 决定下一步”的循环中工作。不要输出思维过程，
每次只输出结构化 action、arguments 和最终 response。

可用工具：
1. inspect_deck()：读取整套课件页面摘要、当前版本、模板和全部可用布局。
2. inspect_slide(slide_id?, order?)：读取一页完整 Markdown、布局、相邻页和已有图片。
3. search_knowledge(query, top_k?)：在项目勾选的知识库中执行 RAG 检索。涉及事实、教材、
   课标或用户资料的修改必须先检索；一般措辞和排版修改无需检索。
4. rewrite_slide(slide_id?, order?, markdown, layout?, title?)：用完整 Markdown 重写一页。
   必须先 inspect_slide；只使用真实存在的模板布局。不得修改稳定 slide_id。
5. place_image(slide_id?, order?, position, caption?)：放置本次附带的图片。position 只能是
   left/right/center/wide/background。你不能判断图片内容，只能依据用户描述、文件名、长宽比和页面结构选位置。
6. remove_image(placement_id)：移除页面中已有图片；placement_id 必须来自 inspect_slide。
7. validate_slide(slide_id?, order?)：检查布局、插槽、文字密度和图片结构。修改后必须调用。
8. finish(response)：结束并给用户简洁说明；不允许声称执行了 observation 中没有成功的操作。

行为要求：
- 修改前先查看目标页面；不清楚目标页时先 inspect_deck。
- 用户说“当前页”时使用请求中的 current_slide_id。
- 可以连续操作，但一次请求最多修改三次。
- 当前 user_message 是本轮唯一需要执行的命令；不得因为历史里出现过修改要求而重复执行旧任务。
- 多轮对话历史只用于理解省略、指代和回答“刚才是否完成”等状态问题，事实仍需通过工具观察。
- 最终 response 必须直接回答当前 user_message，并点明本轮实际修改的页码和内容；
  禁止复制历史回复、重复能力介绍或只说“已完成”。
- 若用户只是问候或询问能力，可以直接 finish，不修改课件。
- 若用户询问“解决了吗、改好了吗、刚才做了什么”，根据历史和本轮 observation 回答，禁止再次修改。
- 页面 Markdown 必须保持 Slidev 可渲染，且布局插槽应符合模板能力。
""".strip()


def _compact(value: Any, limit: int = 12000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else f"{text[:limit]}…"


def specific_agent_response(
    user_message: str,
    observations: list[dict[str, Any]],
    model_response: str,
) -> str:
    """Make mutation replies evidence-based instead of trusting a generic model sentence."""
    successful = [
        item
        for item in observations
        if item.get("ok") and item.get("action") in MUTATING_ACTIONS
    ]
    if not successful:
        return model_response.strip()

    changes: list[str] = []
    for event in successful:
        action = event["action"]
        observation = event.get("observation", {})
        order = observation.get("order")
        page = f"第 {order} 页" if order else "目标页面"
        title = str(observation.get("title") or "").strip()
        page_with_title = f"{page}“{title}”" if title else page
        if action == "rewrite_slide":
            changes.append(f"{page_with_title}已按你的要求完成修改")
        elif action == "place_image":
            position = {
                "left": "左侧",
                "right": "右侧",
                "center": "中间",
                "wide": "下方宽图区域",
                "background": "背景层",
            }.get(observation.get("position"), "指定位置")
            changes.append(f"附件图片已放到{page}的{position}")
        elif action == "remove_image":
            image_name = str(observation.get("image_name") or "").strip()
            changes.append(f"{page}中的图片{f'“{image_name}”' if image_name else ''}已移除")

    validation = next(
        (
            item.get("observation", {})
            for item in reversed(observations)
            if item.get("ok") and item.get("action") == "validate_slide"
        ),
        None,
    )
    if validation and validation.get("valid"):
        check = "，并已检查通过"
    elif validation and validation.get("issues"):
        check = f"。已保存新版本，但检查仍提示：{'；'.join(validation['issues'][:3])}"
    else:
        check = "，并已保存为新版本"

    request = " ".join(user_message.split())
    request_hint = f"（你的要求：{request[:60]}{'…' if len(request) > 60 else ''}）" if request else ""
    return f"已解决：{'；'.join(changes)}{check}。{request_hint}".strip()


def status_agent_response(
    user_message: str,
    history: list[dict[str, Any]],
    model_response: str,
) -> str:
    if not re.search(r"解决了吗|改好了吗|完成了吗|弄好了吗|刚才做了什么|刚才改了什么", user_message):
        return model_response
    previous = next(
        (
            item
            for item in reversed(history)
            if item.get("role") == "assistant" and item.get("actions")
        ),
        None,
    )
    if not previous:
        return model_response
    labels = {
        "rewrite_slide": "页面内容修改",
        "place_image": "图片放置",
        "remove_image": "图片移除",
    }
    completed = [
        labels[action]
        for action in previous.get("actions", [])
        if action in labels
    ]
    if not completed:
        return model_response
    version = previous.get("artifact_version_no")
    version_text = f"，已保存为版本 {version}" if version else "，已保存为新版本"
    return f"已解决：上一轮已完成{'、'.join(dict.fromkeys(completed))}{version_text}。"


def run_editor_react_agent(
    *,
    user_message: str,
    current_slide_id: str,
    project_context: dict[str, Any],
    history: list[dict[str, Any]],
    attachment: dict[str, Any] | None,
    tools: EditorToolbox,
    llm=None,
    trace_id: str | None = None,
) -> EditorAgentResult:
    client = llm or DeepSeekClient()
    run_trace = trace_id or str(uuid.uuid4())
    observations: list[dict[str, Any]] = []
    actions: list[str] = []
    mutation_count = 0
    model_name = ""
    repeated_calls: dict[str, int] = {}

    for step in range(1, MAX_AGENT_STEPS + 1):
        state = {
            "project": project_context,
            "current_slide_id": current_slide_id,
            "attachment": attachment,
            "conversation_history": history[-12:],
            "user_message": user_message,
            "completed_steps": observations,
            "limits": {
                "step": step,
                "max_steps": MAX_AGENT_STEPS,
                "mutations_used": mutation_count,
                "max_mutations": MAX_MUTATIONS,
            },
        }
        decision, result = client.invoke_structured(
            SYSTEM_PROMPT,
            f"当前 ReAct 状态：{_compact(state)}",
            ReActDecision,
            trace_id=run_trace,
        )
        model_name = result.model
        action = decision.action
        if action == "finish":
            response = decision.response.strip()
            if not response:
                response = "已完成本次检查。" if actions else "请告诉我希望修改哪一页以及具体要求。"
            response = specific_agent_response(user_message, observations, response)
            if not any(
                item.get("ok") and item.get("action") in MUTATING_ACTIONS
                for item in observations
            ):
                response = status_agent_response(user_message, history, response)
            return EditorAgentResult(response, run_trace, actions, observations, model_name)

        signature = f"{action}:{_compact(decision.arguments, 3000)}"
        repeated_calls[signature] = repeated_calls.get(signature, 0) + 1
        if repeated_calls[signature] > 2:
            observations.append(
                {
                    "action": action,
                    "ok": False,
                    "error": "同一工具参数已重复执行，必须换一种操作或结束。",
                }
            )
            continue

        if action in MUTATING_ACTIONS:
            if mutation_count >= MAX_MUTATIONS:
                observations.append(
                    {
                        "action": action,
                        "ok": False,
                        "error": "本轮修改次数已达到上限，请结束并让用户确认结果。",
                    }
                )
                continue
            mutation_count += 1

        try:
            observation = tools.execute(action, decision.arguments)
            event = {"action": action, "ok": True, "observation": observation}
            actions.append(action)
        except (ValueError, RuntimeError) as exc:
            event = {"action": action, "ok": False, "error": str(exc)[:800]}
        observations.append(event)

    successful_mutations = [
        item["action"]
        for item in observations
        if item.get("ok") and item.get("action") in MUTATING_ACTIONS
    ]
    fallback_response = (
        "我已完成可安全执行的修改并保存为新版本；由于达到单轮步骤上限，请先查看当前结果，再继续告诉我下一步。"
        if successful_mutations
        else "我检查了当前课件，但在安全步骤上限内没有完成修改。请把目标页和修改要求说得更具体一些。"
    )
    response = specific_agent_response(user_message, observations, fallback_response)
    return EditorAgentResult(response, run_trace, actions, observations, model_name)
