from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Iterable

from app.core.config import get_settings

from .embeddings import EmbeddingProvider, create_embedding_provider, tokenize_zh
from .exceptions import RetrievalError


def _lexical_score(query: str, content: str) -> float:
    query_tokens = set(tokenize_zh(query))
    content_tokens = set(tokenize_zh(content))
    if not query_tokens or not content_tokens:
        return 0.0
    return len(query_tokens & content_tokens) / math.sqrt(len(query_tokens) * len(content_tokens))


def _safe_project_key(project_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id).strip("_-")[:32] or "project"
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:12]
    return f"project_{slug}_{digest}"


class ProjectVectorStore:
    """Project-isolated Chroma adapter with an explicit JSON fallback for tests."""

    def __init__(
        self,
        root: Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        *,
        force_json: bool = False,
    ):
        settings = get_settings()
        self.root = Path(root or settings.chroma_persist_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider or create_embedding_provider()
        self.force_json = force_json
        self._client = None

    @property
    def backend_name(self) -> str:
        return "json-test-fallback" if self.force_json else "chroma"

    @property
    def client(self):
        """Compatibility accessor used by the backend health endpoint."""
        return self._get_client()

    def _get_client(self):
        if self.force_json:
            return None
        if self._client is None:
            try:
                import chromadb

                self._client = chromadb.PersistentClient(path=str(self.root))
            except ImportError as exc:
                raise RetrievalError("缺少 chromadb 依赖，无法使用正式向量库") from exc
            except Exception as exc:
                raise RetrievalError("Chroma 初始化失败，请检查持久化目录") from exc
        return self._client

    def collection_name(self, project_id: str) -> str:
        return _safe_project_key(project_id)

    def _collection(self, project_id: str):
        client = self._get_client()
        return client.get_or_create_collection(
            name=self.collection_name(project_id),
            metadata={"hnsw:space": "cosine", "project_id_hash": hashlib.sha256(project_id.encode()).hexdigest()},
        )

    def _path(self, project_id: str) -> Path:
        return self.root / f"{self.collection_name(project_id)}.json"

    def _load(self, project_id: str) -> list[dict]:
        path = self._path(project_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetrievalError("测试检索存储损坏") from exc

    def _save(self, project_id: str, rows: list[dict]) -> None:
        self._path(project_id).write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")

    @staticmethod
    def _metadata(project_id: str, source_id: str, filename: str, chunk) -> dict:
        return {
            "project_id": project_id,
            "source_id": source_id,
            "chunk_id": chunk.chunk_id,
            "filename": filename,
            "location": chunk.location,
            "content_hash": getattr(chunk, "content_hash", ""),
            "heading": getattr(chunk, "heading", ""),
        }

    def add_documents(self, project_id: str, source_id: str, filename: str, chunks: Iterable) -> int:
        rows = list(chunks)
        if not rows:
            return 0
        metadatas = [self._metadata(project_id, source_id, filename, chunk) for chunk in rows]
        client = self._get_client()
        if client is not None:
            try:
                collection = self._collection(project_id)
                collection.delete(where={"source_id": source_id})
                collection.upsert(
                    ids=[chunk.chunk_id for chunk in rows],
                    documents=[chunk.content for chunk in rows],
                    metadatas=metadatas,
                    embeddings=self.embedding_provider.embed_documents([chunk.content for chunk in rows]),
                )
                return len(rows)
            except Exception as exc:
                raise RetrievalError("资料写入 Chroma 失败") from exc

        saved = [row for row in self._load(project_id) if row["source_id"] != source_id]
        saved.extend({**metadata, "content": chunk.content} for metadata, chunk in zip(metadatas, rows))
        self._save(project_id, saved)
        return len(rows)

    @staticmethod
    def _where(source_ids: list[str] | None) -> dict | None:
        if not source_ids:
            return None
        unique = sorted(set(source_ids))
        return {"source_id": unique[0]} if len(unique) == 1 else {"source_id": {"$in": unique}}

    def similarity_search(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
        source_ids: list[str] | None = None,
        min_score: float | None = None,
    ) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        settings = get_settings()
        threshold = settings.ai_min_score if min_score is None else min_score
        client = self._get_client()
        if client is not None:
            try:
                collection = self._collection(project_id)
                count = collection.count()
                if count == 0:
                    return []
                result = collection.query(
                    query_embeddings=[self.embedding_provider.embed_query(query)],
                    n_results=min(count, max(top_k * 4, top_k)),
                    where=self._where(source_ids),
                    include=["documents", "metadatas", "distances"],
                )
                candidates = []
                for content, metadata, distance in zip(
                    result["documents"][0], result["metadatas"][0], result["distances"][0]
                ):
                    vector_score = max(0.0, min(1.0, 1.0 - float(distance)))
                    lexical = _lexical_score(query, content)
                    score = round(vector_score * 0.75 + lexical * 0.25, 4)
                    candidates.append({**metadata, "content": content, "score": score})
            except Exception as exc:
                raise RetrievalError("Chroma 检索失败") from exc
        else:
            candidates = self._load(project_id)
            if source_ids:
                allowed = set(source_ids)
                candidates = [row for row in candidates if row["source_id"] in allowed]
            candidates = [
                {**row, "score": round(_lexical_score(query, row["content"]), 4)} for row in candidates
            ]

        ranked = sorted(candidates, key=lambda item: (-item["score"], item["chunk_id"]))
        return [row for row in ranked if row["score"] >= threshold][:top_k]

    def delete_by_source(self, project_id: str, source_id: str) -> None:
        client = self._get_client()
        if client is not None:
            try:
                self._collection(project_id).delete(where={"source_id": source_id})
                return
            except Exception as exc:
                raise RetrievalError("从 Chroma 删除资料失败") from exc
        self._save(project_id, [row for row in self._load(project_id) if row["source_id"] != source_id])

    def count(self, project_id: str, source_id: str | None = None) -> int:
        client = self._get_client()
        if client is not None:
            collection = self._collection(project_id)
            if source_id is None:
                return collection.count()
            return len(collection.get(where={"source_id": source_id}, include=[])["ids"])
        rows = self._load(project_id)
        return len([row for row in rows if source_id is None or row["source_id"] == source_id])

    def close(self) -> None:
        """Release embedded Chroma handles, mainly for Windows tests and short-lived tools."""
        self._client = None
        if not self.force_json:
            try:
                from chromadb.api.client import SharedSystemClient

                SharedSystemClient.clear_system_cache()
            except (ImportError, AttributeError):
                pass
