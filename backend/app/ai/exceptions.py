"""AI/RAG 层的稳定异常分类。

底层 httpx、Pydantic、文件解析和向量库异常先转换为这些类型，service 再
决定重试、降级或向 API 返回何种错误码，避免前端依赖第三方异常文本。
"""

from __future__ import annotations


class AIError(RuntimeError):
    """Member 4 public exception base with stable API-facing error codes."""

    code = "AI_ERROR"

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class AIConfigurationError(AIError):
    """模型地址、密钥或 provider 配置不完整。"""
    code = "LLM_NOT_CONFIGURED"


class AIAuthenticationError(AIError):
    """第三方模型拒绝认证。"""
    code = "LLM_AUTH_FAILED"


class AITimeoutError(AIError):
    """模型在配置的超时时间内没有完成。"""
    code = "LLM_TIMEOUT"

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class AIRateLimitError(AIError):
    """模型服务限流；可按 retry_after 决定重试。"""
    code = "LLM_RATE_LIMITED"

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class AINetworkError(AIError):
    """无法连接模型服务或传输中断。"""
    code = "LLM_NETWORK_ERROR"

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class AIStructuredOutputError(AIError):
    """模型结果无法解析/修复为约定结构。"""
    code = "LLM_INVALID_STRUCTURE"


class RetrievalError(AIError):
    """向量检索不可用或结果结构异常。"""
    code = "NO_RETRIEVAL_RESULT"


class IngestionError(AIError):
    """资料格式不支持、解析失败或无法切片入库。"""
    code = "DOCUMENT_PARSE_FAILED"
