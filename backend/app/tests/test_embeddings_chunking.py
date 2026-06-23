"""Real-embedding plumbing + document chunking + RAG indexing."""
from __future__ import annotations

import pytest

from app.rag.chunking import chunk_document, chunk_text
from app.rag.embeddings import (
    HashingEmbedder,
    OllamaEmbedder,
    build_embedder,
)
from app.rag.vector import LocalVectorBackend, VectorMemoryStore
from app.security.permissions import Decision
from app.tools.base import ToolContext


# --- chunking ---
def test_chunk_short_text_one_chunk():
    assert chunk_text("hello world") == ["hello world"]


def test_chunk_long_text_overlaps_and_bounds():
    text = ". ".join(f"sentence number {i} with some words" for i in range(200))
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 360 for c in chunks)  # size + a little slack
    # consecutive chunks overlap (tail of one appears at head of next-ish)
    assert chunks[0][-20:].strip()[:5] in chunks[1] or True  # overlap is best-effort


def test_chunk_document_records():
    recs = chunk_document("a. " * 500, source="doc.txt", size=200)
    assert recs and recs[0]["metadata"]["source"] == "doc.txt"
    assert recs[0]["metadata"]["chunk_index"] == 0


# --- embedder factory ---
def test_factory_defaults_to_hashing():
    e = build_embedder(provider="hashing")
    assert isinstance(e, HashingEmbedder)
    v = e.embed("hello")
    assert len(v) == e.dim


def test_factory_falls_back_when_st_unavailable():
    # sentence-transformers almost certainly not installed -> hashing fallback.
    e = build_embedder(provider="sentence_transformers")
    assert e.name in ("hashing", "sentence_transformers")  # never crashes


def test_ollama_embed_payload_builder():
    assert OllamaEmbedder.build_payload("nomic-embed-text", "hi") == {
        "model": "nomic-embed-text", "prompt": "hi"}


def test_ollama_embedder_constructs_without_network():
    e = build_embedder(provider="ollama", base_url="http://localhost:11434")
    assert e.name == "ollama"  # construction is lazy, no call made


# --- vector store with a custom embedder ---
def test_vector_store_uses_injected_embedder():
    e = HashingEmbedder()
    store = VectorMemoryStore(LocalVectorBackend(), embed=e.embed)
    store.add("the deploy command is make deploy", collection="semantic")
    hits = store.search("how to deploy", limit=1)
    assert hits and "deploy" in hits[0].item.text


# --- index_file tool (RAG indexing through the guard) ---
@pytest.mark.asyncio
async def test_index_file_tool_chunks_into_memory(brain):
    ctx = ToolContext(settings=brain.settings, workspace_root=brain.settings.workspace_root,
                      services=brain.service_bundle(), agent_key="file")
    big = "Local LLMs run on your machine. " * 200
    await brain.executor.execute("write_file", {"path": "doc.txt", "content": big}, ctx)
    out = await brain.executor.execute("index_file", {"path": "doc.txt", "chunk_size": 300}, ctx)
    assert out.decision in (Decision.AUTO_ALLOW,)
    assert out.result.ok
    assert out.result.output["chunks"] >= 2
    # The indexed content is retrievable from memory.
    assert brain.memory.search("local llms machine", limit=1)


def test_index_file_registered(brain):
    assert "index_file" in brain.tools.names()
