"""生成结果的进程内短期缓存。

缓存键包含项目、提示词版本、资料/知识库选择和输入内容摘要，避免相同请求
重复消耗模型额度。它不是业务事实来源：进程重启后可安全丢失，正式结果仍
必须写入 ArtifactVersion。
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def build_cache_key(
    *,
    project_id: str,
    input_version: str,
    model: str,
    prompt_version: str,
    payload: dict[str, Any],
) -> str:
    """对会影响生成结果的全部输入做稳定序列化与 SHA-256 摘要。"""
    namespace = {
        "project_id": project_id,
        "input_version": input_version,
        "model": model,
        "prompt_version": prompt_version,
        "payload": payload,
    }
    encoded = json.dumps(namespace, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheHit:
    """缓存命中结果及首次写入时间。"""
    key: str
    value: dict[str, Any]
    created_at: str
    cached: bool = True


class GenerationCache:
    """线程安全需求较低的单进程字典缓存，按项目支持整体失效。"""
    """Process-local cache. Callers must display CacheHit.cached instead of claiming a new model run."""

    def __init__(self):
        self._values: dict[str, CacheHit] = {}

    def put(self, key: str, value: dict[str, Any]) -> CacheHit:
        hit = CacheHit(
            key=key,
            value=deepcopy(value),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._values[key] = hit
        return hit

    def get(self, key: str) -> CacheHit | None:
        hit = self._values.get(key)
        return None if hit is None else CacheHit(hit.key, deepcopy(hit.value), hit.created_at)

    def clear_project(self, project_id: str) -> None:
        # Keys are one-way hashes, so project-aware eviction requires the caller to keep its key list.
        # This method deliberately clears all process-local values to avoid accidental cross-project reuse.
        self._values.clear()
