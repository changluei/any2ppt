from app.ai.editor_agent import SYSTEM_PROMPT, run_editor_react_agent, status_agent_response
from app.ai.llm_client import LLMResult


class FakeLLM:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def invoke_structured(self, _system, _user, output_model, *, trace_id=None):
        decision = output_model.model_validate(next(self.decisions))
        return decision, LLMResult(
            text="{}",
            model="fake-deepseek",
            elapsed_ms=1,
            trace_id=trace_id or "trace",
        )


class RecordingTools:
    def __init__(self):
        self.calls = []

    def execute(self, action, arguments):
        self.calls.append((action, arguments))
        if action == "inspect_slide":
            return {"slide": {"slide_id": "SLIDE-03", "markdown": "# 原标题"}}
        if action == "rewrite_slide":
            return {
                "changed": True,
                "version_no": 2,
                "order": 3,
                "title": "新标题",
            }
        if action == "validate_slide":
            return {"valid": True, "issues": []}
        raise AssertionError(action)


def test_editor_agent_runs_action_observation_loop_without_exposing_reasoning():
    tools = RecordingTools()
    llm = FakeLLM(
        [
            {"action": "inspect_slide", "arguments": {"order": 3}},
            {
                "action": "rewrite_slide",
                "arguments": {
                    "slide_id": "SLIDE-03",
                    "markdown": "# 新标题\n\n- 精简后的内容",
                },
            },
            {"action": "validate_slide", "arguments": {"slide_id": "SLIDE-03"}},
            {"action": "finish", "arguments": {}, "response": "第 3 页已精简并检查通过。"},
        ]
    )

    result = run_editor_react_agent(
        user_message="精简第 3 页",
        current_slide_id="SLIDE-01",
        project_context={"project_id": "project-1"},
        history=[],
        attachment=None,
        tools=tools,
        llm=llm,
        trace_id="trace-1",
    )

    assert result.response == "已解决：第 3 页“新标题”已按你的要求完成修改，并已检查通过。（你的要求：精简第 3 页）"
    assert result.actions == ["inspect_slide", "rewrite_slide", "validate_slide"]
    assert [call[0] for call in tools.calls] == result.actions
    assert all("thought" not in event for event in result.observations)
    assert "不能看见图片像素" in SYSTEM_PROMPT


def test_editor_agent_tells_model_that_attachment_has_no_vision():
    tools = RecordingTools()
    captured = {}

    class CapturingLLM:
        def invoke_structured(self, system, user, output_model, *, trace_id=None):
            captured["system"] = system
            captured["user"] = user
            return output_model.model_validate(
                {"action": "finish", "arguments": {}, "response": "请说明图片用途。"}
            ), LLMResult(text="{}", model="fake", elapsed_ms=1, trace_id=trace_id or "")

    run_editor_react_agent(
        user_message="使用这张图",
        current_slide_id="SLIDE-01",
        project_context={"project_id": "project-1"},
        history=[],
        attachment={
            "image_id": "image-1",
            "filename": "课堂照片.png",
            "width": 1280,
            "height": 720,
            "vision_available": False,
        },
        tools=tools,
        llm=CapturingLLM(),
    )

    assert "不能看见图片像素" in captured["system"]
    assert '"vision_available":false' in captured["user"]


def test_status_reply_uses_previous_actual_actions_instead_of_repeating_capabilities():
    response = status_agent_response(
        "刚才改好了吗？",
        [
            {
                "role": "assistant",
                "content": "旧的通用能力介绍",
                "actions": ["inspect_slide", "rewrite_slide", "validate_slide"],
                "artifact_version_no": 8,
            }
        ],
        "我可以查看课件、修改页面……",
    )
    assert response == "已解决：上一轮已完成页面内容修改，已保存为版本 8。"
