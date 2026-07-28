from __future__ import annotations

import json
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
- 多轮对话历史只用于理解省略和指代，事实仍需通过工具观察。
- 若用户只是问候或询问能力，可以直接 finish，不修改课件。
- 页面 Markdown 必须保持 Slidev 可渲染，且布局插槽应符合模板能力。
""".strip()


def _compact(value: Any, limit: int = 12000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else f"{text[:limit]}…"


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
    response = (
        "我已完成可安全执行的修改并保存为新版本；由于达到单轮步骤上限，请先查看当前结果，再继续告诉我下一步。"
        if successful_mutations
        else "我检查了当前课件，但在安全步骤上限内没有完成修改。请把目标页和修改要求说得更具体一些。"
    )
    return EditorAgentResult(response, run_trace, actions, observations, model_name)
