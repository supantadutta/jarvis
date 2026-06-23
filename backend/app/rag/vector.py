"""Pluggable vector memory backends (Phase 1/2 roadmap: "Qdrant or Chroma").

Default is a dependency-free local embedding (deterministic hashing bag-of-words)
+ in-memory cosine index, so semantic-style retrieval works offline with no model
download and no external service. Chroma and Qdrant adapters are provided behind
the same `VectorBackend` interface and imported lazily.

`VectorMemoryStore` wraps any `VectorBackend` with the same surface as the lexical
`MemoryStore` (add / search / collections / count), so it is a drop-in.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.rag.memory import MemoryItem, SearchHit

_TOKEN = re.compile(r"[a-z0-9]+")
DEFAULT_DIM = 256


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class EmbeddingFn(Protocol):
    dim: int

    def __call__(self, text: str) -> list[float]: ...


class HashingEmbedding:
    """Deterministic, offline embedding: hashes tokens into a fixed-dim vector
    (signed hashing trick) and L2-normalizes. No model, no network."""

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim

    @staticmethod
    def _stable_hash(token: str) -> int:
        # Stable across processes/restarts (unlike builtin hash() which is salted).
        import hashlib

        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")

    def __call__(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokens(text):
            h = self._stable_hash(tok)
            idx = h % self.dim
            sign = 1.0 if (h >> 32) & 1 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class VectorBackend(Protocol):
    def upsert(self, id: str, vector: list[float], payload: dict) -> None: ...
    def query(self, vector: list[float], k: int, collection: str | None) -> list[tuple[dict, float]]: ...
    def count(self) -> int: ...
    def collections(self) -> dict[str, int]: ...


@dataclass
class LocalVectorBackend:
    """In-memory cosine index. Real vector retrieval, zero dependencies."""

    _rows: dict[str, tuple[list[float], dict]] = field(default_factory=dict)

    def upsert(self, id: str, vector: list[float], payload: dict) -> None:
        self._rows[id] = (vector, payload)

    def query(self, vector: list[float], k: int, collection: str | None) -> list[tuple[dict, float]]:
        scored: list[tuple[dict, float]] = []
        for vec, payload in self._rows.values():
            if collection and payload.get("collection") != collection:
                continue
            scored.append((payload, cosine(vector, vec)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def count(self) -> int:
        return len(self._rows)

    def collections(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for _, payload in self._rows.values():
            c = payload.get("collection", "default")
            out[c] = out.get(c, 0) + 1
        return out


class VectorMemoryStore:
    """MemoryStore-compatible store backed by a VectorBackend + embedding fn."""

    def __init__(self, backend: VectorBackend | None = None, embed: EmbeddingFn | None = None) -> None:
        self.backend = backend or LocalVectorBackend()
        self.embed = embed or HashingEmbedding()
        self.on_add = None  # optional callback(MemoryItem) for write-through

    def add(self, text: str, *, collection: str = "default",
            metadata: dict | None = None, source: str | None = None) -> MemoryItem:
        item = MemoryItem(
            id=uuid.uuid4().hex[:12], text=text, collection=collection,
            metadata=metadata or {}, source=source,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        payload = {"id": item.id, "text": text, "collection": collection,
                   "source": source, "metadata": item.metadata}
        self.backend.upsert(item.id, self.embed(text), payload)
        if self.on_add is not None:
            try:
                self.on_add(item)
            except Exception:  # noqa: BLE001
                pass
        return item

    def load_item(self, item: MemoryItem) -> None:
        payload = {"id": item.id, "text": item.text, "collection": item.collection,
                   "source": item.source, "metadata": item.metadata}
        self.backend.upsert(item.id, self.embed(item.text), payload)

    def search(self, query: str, *, collection: str | None = None, limit: int = 5) -> list[SearchHit]:
        if not query.strip():
            return []
        hits = self.backend.query(self.embed(query), limit, collection)
        out: list[SearchHit] = []
        for payload, score in hits:
            if score <= 0:
                continue
            item = MemoryItem(
                id=payload["id"], text=payload["text"], collection=payload["collection"],
                metadata=payload.get("metadata", {}), source=payload.get("source"),
            )
            out.append(SearchHit(item=item, score=round(float(score), 4)))
        return out

    def collections(self) -> dict[str, int]:
        return self.backend.collections()

    def count(self) -> int:
        return self.backend.count()


# --- external adapters (lazy; same VectorBackend interface) ---
class ChromaVectorBackend:  # pragma: no cover - external dependency
    def __init__(self, path: str, collection: str = "jarvis") -> None:
        try:
            import chromadb
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("`pip install chromadb` to use the Chroma backend.") from exc
        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(collection)

    def upsert(self, id: str, vector: list[float], payload: dict) -> None:
        self._col.upsert(ids=[id], embeddings=[vector],
                         metadatas=[{k: v for k, v in payload.items() if k != "text"}],
                         documents=[payload.get("text", "")])

    def query(self, vector: list[float], k: int, collection: str | None) -> list[tuple[dict, float]]:
        res = self._col.query(query_embeddings=[vector], n_results=k)
        out = []
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                                   res["distances"][0], strict=False):
            payload = dict(meta)
            payload["text"] = doc
            out.append((payload, 1.0 - float(dist)))
        return out

    def count(self) -> int:
        return self._col.count()

    def collections(self) -> dict[str, int]:
        return {self._col.name: self._col.count()}


class QdrantVectorBackend:  # pragma: no cover - external dependency
    def __init__(self, url: str, collection: str = "jarvis", dim: int = DEFAULT_DIM) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("`pip install qdrant-client` to use the Qdrant backend.") from exc
        self._client = QdrantClient(url=url)
        self._collection = collection
        try:
            self._client.get_collection(collection)
        except Exception:  # noqa: BLE001
            self._client.create_collection(
                collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    def upsert(self, id: str, vector: list[float], payload: dict) -> None:
        from qdrant_client.models import PointStruct

        # Qdrant needs int/UUID ids; map hex id to int.
        self._client.upsert(self._collection,
                            points=[PointStruct(id=int(id, 16), vector=vector, payload=payload)])

    def query(self, vector: list[float], k: int, collection: str | None) -> list[tuple[dict, float]]:
        res = self._client.search(self._collection, query_vector=vector, limit=k)
        return [(p.payload, float(p.score)) for p in res]

    def count(self) -> int:
        return self._client.count(self._collection).count

    def collections(self) -> dict[str, int]:
        return {self._collection: self.count()}
