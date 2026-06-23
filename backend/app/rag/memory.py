"""Local RAG / memory store.

Phase 1 ships a dependency-free in-memory store with a simple lexical
(bag-of-words cosine) retriever so memory add/search works out of the box with
no Qdrant/Chroma/embedding model. The interface matches what a vector backend
would expose, so Chroma/Qdrant can be dropped in for Phase 2 without changing
callers.
"""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class MemoryItem:
    id: str
    text: str
    collection: str
    metadata: dict = field(default_factory=dict)
    source: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    _vec: Counter = field(default_factory=Counter, repr=False)


@dataclass
class SearchHit:
    item: MemoryItem
    score: float


class MemoryStore:
    """Lexical cosine retriever. Swap for a vector store in Phase 2."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}
        self.on_add = None  # optional callback(MemoryItem) for write-through

    def add(
        self,
        text: str,
        *,
        collection: str = "default",
        metadata: dict | None = None,
        source: str | None = None,
    ) -> MemoryItem:
        item = MemoryItem(
            id=uuid.uuid4().hex[:12],
            text=text,
            collection=collection,
            metadata=metadata or {},
            source=source,
            _vec=Counter(_tokens(text)),
        )
        self._items[item.id] = item
        if self.on_add is not None:
            try:
                self.on_add(item)
            except Exception:  # noqa: BLE001 - persistence must not break memory
                pass
        return item

    def load_item(self, item: MemoryItem) -> None:
        """Insert a pre-built item (e.g. hydrated from DB) without re-persisting."""
        self._items[item.id] = item

    def get(self, item_id: str) -> MemoryItem | None:
        return self._items.get(item_id)

    def search(
        self, query: str, *, collection: str | None = None, limit: int = 5
    ) -> list[SearchHit]:
        qvec = Counter(_tokens(query))
        if not qvec:
            return []
        hits: list[SearchHit] = []
        for item in self._items.values():
            if collection and item.collection != collection:
                continue
            score = _cosine(qvec, item._vec)
            if score > 0:
                hits.append(SearchHit(item=item, score=round(score, 4)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def collections(self) -> dict[str, int]:
        out: Counter = Counter()
        for item in self._items.values():
            out[item.collection] += 1
        return dict(out)

    def count(self) -> int:
        return len(self._items)


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
