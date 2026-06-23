"""Document chunking for RAG indexing (pure, deterministic, tested).

Splits long text into overlapping, sentence-aware chunks so retrieval returns
focused passages instead of whole documents. No external dependency.
"""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, *, size: int = 800, overlap: int = 120) -> list[str]:
    """Chunk `text` into ~`size`-char pieces with `overlap`, breaking on sentence
    boundaries where possible."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    sentences = _SENT.split(text)
    chunks: list[str] = []
    cur = ""
    for sent in sentences:
        if len(cur) + len(sent) + 1 <= size:
            cur = f"{cur} {sent}".strip()
        else:
            if cur:
                chunks.append(cur)
            # Start the next chunk with an overlap tail of the previous one.
            tail = cur[-overlap:] if overlap and cur else ""
            cur = f"{tail} {sent}".strip() if tail else sent
            # A single sentence longer than `size` is hard-split.
            while len(cur) > size:
                chunks.append(cur[:size])
                cur = cur[size - overlap :]
    if cur:
        chunks.append(cur)
    return chunks


def chunk_document(text: str, *, source: str | None = None,
                   size: int = 800, overlap: int = 120) -> list[dict]:
    """Chunk into records ready for memory.add (text + metadata)."""
    return [
        {"text": c, "metadata": {"source": source, "chunk_index": i, "chunks": None}}
        for i, c in enumerate(chunk_text(text, size=size, overlap=overlap))
    ]
