from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Optional
from app.core.config import get_settings
from .exceptions import AIConfigurationError, AITimeoutError, AIError


@dataclass
class LLMResult:
    text: str
    model: str
    elapsed_ms: int
    usage: Optional[dict] = None


class DeepSeekClient:
    def __init__(self):
        self.settings = get_settings()

    def invoke(self, system: str, user: str, json_schema: Optional[dict] = None) -> LLMResult:
        if not self.settings.deepseek_api_key:
            raise AIConfigurationError("未配置 DEEPSEEK_API_KEY，无法执行真实模型生成")
        try:
            from openai import OpenAI, APITimeoutError, AuthenticationError, RateLimitError
        except ImportError as exc:
            raise AIConfigurationError("缺少 openai 依赖") from exc
        try:
            client = OpenAI(api_key=self.settings.deepseek_api_key, base_url=self.settings.deepseek_base_url, timeout=self.settings.ai_timeout_seconds)
            started = time.perf_counter()
            options = dict(
                model=self.settings.deepseek_model,
                temperature=self.settings.ai_temperature,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            if json_schema:
                options["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**options)
            return LLMResult(
                text=response.choices[0].message.content or "",
                model=response.model,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                usage=response.usage.model_dump() if response.usage else None,
            )
        except APITimeoutError as exc:
            raise AITimeoutError("DeepSeek 调用超时，请稍后重试") from exc
        except AuthenticationError as exc:
            raise AIConfigurationError("DeepSeek 鉴权失败，请检查密钥") from exc
        except RateLimitError as exc:
            raise AIError("模型限流，请稍后重试") from exc

    def invoke_json(self, system: str, user: str) -> tuple[dict, LLMResult]:
        result = self.invoke(system, user, {"type": "object"})
        try:
            return json.loads(result.text), result
        except json.JSONDecodeError as exc:
            raise AIError("模型返回的结构无法解析") from exc
