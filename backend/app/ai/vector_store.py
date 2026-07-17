from __future__ import annotations
import json
import math
import re
import hashlib
from pathlib import Path
from typing import Optional
from app.core.config import get_settings


def _tokens(text: str) -> set[str]:
    chinese = [text[i:i + 2] for i in range(max(0, len(text) - 1)) if "\u4e00" <= text[i] <= "\u9fff"]
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return set(chinese + words)


def _score(query: str, content: str) -> float:
    q, c = _tokens(query), _tokens(content)
    if not q or not c:
        return 0.0
    return len(q & c) / math.sqrt(len(q) * len(c))


class ProjectVectorStore:
    """Chroma 持久化适配器；未安装 AI 扩展时使用同接口 JSON 降级。"""
    def __init__(self):
        self.root = get_settings().chroma_persist_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.client = None
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=str(self.root))
        except ImportError:
            pass

    @staticmethod
    def _embedding(text: str, size: int = 256) -> list[float]:
        vector = [0.0] * size
        for token in _tokens(text):
            index = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % size
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def _collection(self, project_id: str):
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id)[:48]
        return self.client.get_or_create_collection(name=f"project_{safe}", metadata={"hnsw:space": "cosine"})

    def _path(self, project_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id)
        return self.root / f"project_{safe}.json"

    def _load(self, project_id: str) -> list[dict]:
        path = self._path(project_id)
        return json.loads(path.read_text("utf-8")) if path.exists() else []

    def _save(self, project_id: str, rows: list[dict]):
        self._path(project_id).write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")

    def add_documents(self, project_id: str, source_id: str, filename: str, chunks) -> int:
        if self.client:
            collection = self._collection(project_id)
            collection.delete(where={"source_id": source_id})
            rows = list(chunks)
            collection.upsert(
                ids=[c.chunk_id for c in rows], documents=[c.content for c in rows],
                metadatas=[{"project_id": project_id, "source_id": source_id, "chunk_id": c.chunk_id, "filename": filename, "location": c.location} for c in rows],
                embeddings=[self._embedding(c.content) for c in rows],
            )
            return len(rows)
        rows = [row for row in self._load(project_id) if row["source_id"] != source_id]
        rows.extend({"project_id": project_id, "source_id": source_id, "chunk_id": c.chunk_id, "filename": filename, "location": c.location, "content": c.content} for c in chunks)
        self._save(project_id, rows)
        return len(chunks)

    def similarity_search(self, project_id: str, query: str, top_k: int = 5, source_ids: Optional[list[str]] = None) -> list[dict]:
        if self.client:
            where = {"source_id": {"$in": source_ids}} if source_ids else None
            result = self._collection(project_id).query(query_embeddings=[self._embedding(query)], n_results=top_k, where=where, include=["documents", "metadatas", "distances"])
            output = []
            for content, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
                output.append({**metadata, "content": content, "score": round(max(0.0, 1.0 - distance), 4)})
            return [row for row in output if row["score"] > 0]
        rows = self._load(project_id)
        if source_ids:
            rows = [row for row in rows if row["source_id"] in source_ids]
        ranked = sorted(({**row, "score": round(_score(query, row["content"]), 4)} for row in rows), key=lambda item: item["score"], reverse=True)
        return [row for row in ranked[:top_k] if row["score"] > 0]

    def delete_by_source(self, project_id: str, source_id: str) -> None:
        if self.client:
            self._collection(project_id).delete(where={"source_id": source_id})
            return
        self._save(project_id, [row for row in self._load(project_id) if row["source_id"] != source_id])
