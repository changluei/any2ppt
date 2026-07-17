class AIError(RuntimeError):
    code = "AI_ERROR"


class AIConfigurationError(AIError):
    code = "LLM_AUTH_FAILED"


class AITimeoutError(AIError):
    code = "LLM_TIMEOUT"


class RetrievalError(AIError):
    code = "NO_RETRIEVAL_RESULT"

