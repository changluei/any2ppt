from __future__ import annotations


class AIError(RuntimeError):
    """Member 4 public exception base with stable API-facing error codes."""

    code = "AI_ERROR"

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class AIConfigurationError(AIError):
    code = "LLM_NOT_CONFIGURED"


class AIAuthenticationError(AIError):
    code = "LLM_AUTH_FAILED"


class AITimeoutError(AIError):
    code = "LLM_TIMEOUT"

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class AIRateLimitError(AIError):
    code = "LLM_RATE_LIMITED"

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class AINetworkError(AIError):
    code = "LLM_NETWORK_ERROR"

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class AIStructuredOutputError(AIError):
    code = "LLM_INVALID_STRUCTURE"


class RetrievalError(AIError):
    code = "NO_RETRIEVAL_RESULT"


class IngestionError(AIError):
    code = "DOCUMENT_PARSE_FAILED"

