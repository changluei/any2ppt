from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

from .exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIError,
    AINetworkError,
    AIRateLimitError,
    AIStructuredOutputError,
    AITimeoutError,
)


TModel = TypeVar("TModel", bound=BaseModel)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    elapsed_ms: int
    usage: dict[str, Any] | None = None
    attempts: int = 1
    trace_id: str = ""
    prompt_version: str = ""


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AIStructuredOutputError("模型返回的内容不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise AIStructuredOutputError("模型结构化输出必须是 JSON 对象")
    return value


class DeepSeekClient:
    """OpenAI-compatible DeepSeek adapter; SDK calls never leak into business code."""

    def __init__(self, settings=None, client_factory: Callable[..., Any] | None = None):
        self.settings = settings or get_settings()
        self._client_factory = client_factory

    @property
    def configured(self) -> bool:
        return bool(self.settings.deepseek_api_key.strip()) and not getattr(
            self.settings, "ai_force_fallback", False
        )

    def _client(self):
        if not self.configured:
            raise AIConfigurationError("未配置 DEEPSEEK_API_KEY，无法执行真实模型生成")
        if self._client_factory:
            return self._client_factory(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.ai_timeout_seconds,
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigurationError("缺少 openai 依赖") from exc
        return OpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            timeout=self.settings.ai_timeout_seconds,
        )

    def invoke(
        self,
        system: str,
        user: str,
        json_schema: dict | None = None,
        *,
        trace_id: str | None = None,
    ) -> LLMResult:
        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                AuthenticationError,
                RateLimitError,
            )
        except ImportError as exc:
            raise AIConfigurationError("缺少 openai 依赖") from exc

        client = self._client()
        request_trace = trace_id or str(uuid.uuid4())
        started = time.perf_counter()
        max_attempts = max(1, self.settings.ai_max_retries + 1)
        last_error: AIError | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                options: dict[str, Any] = {
                    "model": self.settings.deepseek_model,
                    "temperature": self.settings.ai_temperature,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if json_schema is not None:
                    options["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**options)
                return LLMResult(
                    text=response.choices[0].message.content or "",
                    model=response.model or self.settings.deepseek_model,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    usage=response.usage.model_dump() if response.usage else None,
                    attempts=attempt,
                    trace_id=request_trace,
                    prompt_version=self.settings.ai_prompt_version,
                )
            except AuthenticationError as exc:
                raise AIAuthenticationError("DeepSeek 鉴权失败，请检查密钥") from exc
            except APITimeoutError as exc:
                last_error = AITimeoutError("DeepSeek 调用超时，请稍后重试")
                last_error.__cause__ = exc
            except RateLimitError as exc:
                last_error = AIRateLimitError("模型限流，请稍后重试")
                last_error.__cause__ = exc
            except APIConnectionError as exc:
                last_error = AINetworkError("无法连接 DeepSeek 服务，请检查网络")
                last_error.__cause__ = exc
            except APIStatusError as exc:
                if exc.status_code >= 500:
                    last_error = AINetworkError("DeepSeek 服务暂时不可用")
                    last_error.__cause__ = exc
                else:
                    raise AIError(f"DeepSeek 请求失败（HTTP {exc.status_code}）") from exc
            if attempt < max_attempts:
                time.sleep(min(1.5, 0.2 * (2 ** (attempt - 1))))
        assert last_error is not None
        raise last_error

    def invoke_json(self, system: str, user: str, *, trace_id: str | None = None) -> tuple[dict, LLMResult]:
        result = self.invoke(system, user, {"type": "object"}, trace_id=trace_id)
        return _extract_json(result.text), result

    def invoke_structured(
        self,
        system: str,
        user: str,
        output_model: type[TModel],
        *,
        trace_id: str | None = None,
    ) -> tuple[TModel, LLMResult]:
        schema = output_model.model_json_schema()
        result = self.invoke(system, user, schema, trace_id=trace_id)
        try:
            return output_model.model_validate(_extract_json(result.text)), result
        except (ValidationError, AIStructuredOutputError) as first_error:
            if self.settings.ai_json_repair_attempts < 1:
                raise AIStructuredOutputError("模型输出未通过结构校验") from first_error
            repair_user = (
                "请只修复下面 JSON 的结构，不改变事实，不新增引用。"
                f"\n目标 JSON Schema：{json.dumps(schema, ensure_ascii=False)}"
                f"\n校验错误：{str(first_error)[:1500]}"
                f"\n待修复内容：{result.text[:6000]}"
            )
            repaired = self.invoke(
                "你是 JSON 结构修复器。只输出一个合法 JSON 对象。",
                repair_user,
                schema,
                trace_id=result.trace_id,
            )
            try:
                return output_model.model_validate(_extract_json(repaired.text)), repaired
            except (ValidationError, AIStructuredOutputError) as exc:
                raise AIStructuredOutputError("模型输出自动修复后仍未通过结构校验") from exc
