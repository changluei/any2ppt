from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence

from app.core.config import get_settings

from .exceptions import AIConfigurationError, AINetworkError


def tokenize_zh(text: str) -> list[str]:
    """Small deterministic tokenizer that works offline for Chinese teaching text."""
    normalized = re.sub(r"\s+", "", text.lower())
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    tokens: list[str] = []
    for run in chinese_runs:
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    tokens.extend(re.findall(r"[a-z0-9_]+", text.lower()))
    return tokens


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Lightweight, reproducible fallback; no model download and no network call."""

    name = "hash-zh-v1"

    def __init__(self, dimensions: int = 384):
        if dimensions < 64:
            raise ValueError("Embedding 维度不能小于 64")
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize_zh(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] & 1 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAICompatibleEmbeddingProvider:
    """Optional remote embedding adapter for an explicitly configured provider."""

    def __init__(self, *, api_key: str, base_url: str, model: str, dimensions: int):
        if not api_key or not base_url or not model:
            raise AIConfigurationError("远程 Embedding 需要配置 API key、base_url 和 model")
        self.name = model
        self.dimensions = dimensions
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(model=self.name, input=list(texts))
            return [item.embedding for item in response.data]
        except Exception as exc:
            raise AINetworkError("Embedding 服务暂时不可用") from exc

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def create_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider.lower() in {"hash", "local_hash"}:
        return HashEmbeddingProvider(settings.embedding_dimensions)
    if settings.embedding_provider.lower() in {"openai", "openai_compatible"}:
        return OpenAICompatibleEmbeddingProvider(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    raise AIConfigurationError(f"不支持的 Embedding provider：{settings.embedding_provider}")
