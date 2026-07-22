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
    key: str
    value: dict[str, Any]
    created_at: str
    cached: bool = True


class GenerationCache:
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
