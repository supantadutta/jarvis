"""Pluggable text embeddings for real semantic memory/RAG.

Default `hashing` is offline + deterministic (no model/service) so tests and
pure-local installs work. `ollama` uses a local embedding model (e.g.
nomic-embed-text) via Ollama — still local-first — and `sentence_transformers`
uses a local ST model. All heavy deps and the network call are lazy; the factory
falls back to hashing if the chosen backend is unavailable, so memory never
breaks.
"""
from __future__ import annotations

from typing import Protocol

from app.rag.vector import DEFAULT_DIM, HashingEmbedding


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Offline deterministic embedder (the existing hashing trick)."""

    name = "hashing"

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim
        self._h = HashingEmbedding(dim)

    def embed(self, text: str) -> list[float]:
        return self._h(text)


class OllamaEmbedder:
    """Local embeddings via Ollama /api/embeddings (e.g. nomic-embed-text)."""

    name = "ollama"

    def __init__(self, base_url: str, model: str = "nomic-embed-text", dim: int = 768) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim

    @staticmethod
    def build_payload(model: str, text: str) -> dict:
        return {"model": model, "prompt": text}

    def embed(self, text: str) -> list[float]:  # pragma: no cover - needs Ollama
        import httpx

        with httpx.Client(timeout=30) as c:
            r = c.post(f"{self.base_url}/api/embeddings",
                       json=self.build_payload(self.model, text))
            r.raise_for_status()
            return r.json()["embedding"]


class SentenceTransformerEmbedder:
    """Local embeddings via sentence-transformers (no network after download)."""

    name = "sentence_transformers"

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # noqa: F401  (raises if absent)

        self._model = SentenceTransformer(model)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:  # pragma: no cover - heavy dep
        return self._model.encode(text, normalize_embeddings=True).tolist()


def build_embedder(*, provider: str = "hashing", base_url: str = "http://localhost:11434",
                   model: str = "nomic-embed-text") -> Embedder:
    """Build the configured embedder, falling back to hashing on any failure."""
    provider = (provider or "hashing").lower()
    try:
        if provider == "ollama":
            return OllamaEmbedder(base_url, model)
        if provider in ("sentence_transformers", "st"):
            return SentenceTransformerEmbedder(model if "/" in model else "all-MiniLM-L6-v2")
    except Exception:  # noqa: BLE001 - degrade gracefully
        import logging

        logging.getLogger("jarvis").warning(
            "Embedding provider '%s' unavailable; using offline hashing embedder.", provider)
    return HashingEmbedder()
