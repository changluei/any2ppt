import pytest

from app.ai.llm_client import DeepSeekClient


client = DeepSeekClient()


@pytest.mark.skipif(not client.configured, reason="未配置 DEEPSEEK_API_KEY，真实模型测试按计划跳过")
def test_real_deepseek_minimal_json_call():
    data, result = client.invoke_json(
        "你是连通性测试助手，只输出 JSON。",
        '返回 {"status":"ok"}，不要添加其他字段。',
        trace_id="deepseek-smoke",
    )
    assert data.get("status") == "ok"
    assert result.model
    assert result.elapsed_ms >= 0
