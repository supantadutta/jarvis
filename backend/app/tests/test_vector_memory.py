"""Pluggable vector memory: offline embeddings + cosine retrieval + backend select."""
from __future__ import annotations

from app.config import Settings
from app.rag.vector import (
    DEFAULT_DIM,
    HashingEmbedding,
    LocalVectorBackend,
    VectorMemoryStore,
    cosine,
)
from app.services.container import Brain


def test_hashing_embedding_is_deterministic_and_normalized():
    e = HashingEmbedding()
    v1 = e("the quick brown fox")
    v2 = e("the quick brown fox")
    assert v1 == v2
    assert len(v1) == DEFAULT_DIM
    # L2-normalized
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6


def test_cosine_similar_texts_score_higher():
    e = HashingEmbedding()
    a = e("wifi password for the home router")
    near = e("home router wifi password")
    far = e("quarterly financial revenue report")
    assert cosine(a, near) > cosine(a, far)


def test_vector_memory_store_add_and_search():
    store = VectorMemoryStore(LocalVectorBackend())
    store.add("the wifi password is in the vault", collection="notes", source="note1")
    store.add("the dog likes to play fetch in the park", collection="notes")
    hits = store.search("where is my wifi password", limit=2)
    assert hits
    assert "wifi password" in hits[0].item.text
    assert store.count() == 2
    assert store.collections()["notes"] == 2


def test_vector_memory_collection_filter():
    store = VectorMemoryStore(LocalVectorBackend())
    store.add("alpha content here", collection="a")
    store.add("beta content here", collection="b")
    hits = store.search("content", collection="a", limit=5)
    assert all(h.item.collection == "a" for h in hits)


def test_brain_selects_local_vector_backend(tmp_path):
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/t.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        vector_backend="local_vector", allow_low_risk_write=True,
    )
    s.ensure_dirs()
    brain = Brain(s, use_mock=True)
    assert isinstance(brain.memory, VectorMemoryStore)
    brain.memory.add("jarvis remembers the plan")
    assert brain.memory.search("plan")  # retrieval works end-to-end


def test_brain_unknown_backend_falls_back_to_lexical(tmp_path):
    from app.rag.memory import MemoryStore

    s = Settings(
        database_url=f"sqlite:///{tmp_path}/t.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        vector_backend="qdrant",  # qdrant-client not installed -> graceful fallback
    )
    s.ensure_dirs()
    brain = Brain(s, use_mock=True)
    assert isinstance(brain.memory, MemoryStore)
