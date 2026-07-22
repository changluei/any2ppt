from types import SimpleNamespace

import pytest

from app.ai.exceptions import AIConfigurationError, AIStructuredOutputError
from app.ai.llm_client import DeepSeekClient
from app.ai.skills import CourseStandardOutput


def _settings(**overrides):
    values = {
        "deepseek_api_key": "test-key-never-logged",
        "deepseek_base_url": "https://example.invalid",
        "deepseek_model": "deepseek-chat",
        "ai_timeout_seconds": 5,
        "ai_temperature": 0.2,
        "ai_max_retries": 0,
        "ai_json_repair_attempts": 1,
        "ai_prompt_version": "test-v1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def __init__(self, text):
        self.model = "fake-deepseek"
        self.usage = None
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]


class FakeCompletions:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **options):
        self.calls.append(options)
        return FakeResponse(self.outputs.pop(0))


class FakeSDK:
    def __init__(self, outputs):
        self.chat = SimpleNamespace(completions=FakeCompletions(outputs))


def test_no_key_stops_before_sdk_creation():
    called = False

    def factory(**_kwargs):
        nonlocal called
        called = True

    client = DeepSeekClient(_settings(deepseek_api_key=""), factory)
    with pytest.raises(AIConfigurationError):
        client.invoke("system", "user")
    assert called is False


def test_structured_output_repairs_once_and_keeps_trace_id():
    sdk = FakeSDK([
        '{"requirements": []}',
        '{"requirements":["观察并解释蒸发现象"],"key_concepts":["蒸发"],"evidence_summary":"依据给定资料","general_suggestions":[]}',
    ])
    client = DeepSeekClient(_settings(), lambda **_kwargs: sdk)
    output, result = client.invoke_structured("system", "user", CourseStandardOutput, trace_id="trace-json")
    assert output.requirements == ["观察并解释蒸发现象"]
    assert result.trace_id == "trace-json"
    assert len(sdk.chat.completions.calls) == 2
    assert all(call["response_format"] == {"type": "json_object"} for call in sdk.chat.completions.calls)


def test_structured_output_fails_after_single_repair():
    sdk = FakeSDK(["not-json", "still-not-json"])
    client = DeepSeekClient(_settings(), lambda **_kwargs: sdk)
    with pytest.raises(AIStructuredOutputError, match="自动修复后"):
        client.invoke_structured("system", "user", CourseStandardOutput)
    assert len(sdk.chat.completions.calls) == 2
