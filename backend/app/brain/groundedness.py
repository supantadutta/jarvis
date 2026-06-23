"""Groundedness / factuality check (Cognitive Processing Engine v2).

A deterministic factuality proxy: does the answer's content actually appear in
the retrieved evidence (memory hits, web/tool observations)? For each sentence in
the answer we measure lexical containment against the source corpus; sentences
with low support are flagged as potentially unsupported (hallucination risk).

This gives the learning loop a *real* signal that doesn't depend on an LLM
verifier (which in tests is mocked). It's a proxy, not ground truth — but it
catches answers that invent content not present in the provided sources.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")
_SENT = re.compile(r"(?<=[.!?])\s+")
# Common words that shouldn't count toward "support".
_STOP = frozenset(
    "the a an and or but if then else of to in on at for with without is are was "
    "were be been being this that these those it its as by from into over under "
    "you your i we they he she them his her our their can will would should could "
    "may might do does did not no yes so such than".split()
)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2}


@dataclass
class Groundedness:
    score: float                       # 0..1 fraction of supported sentences
    supported: int
    total: int
    unsupported: list[str]             # sentences with weak support

    def public(self) -> dict:
        return {"score": round(self.score, 3), "supported": self.supported,
                "total": self.total, "unsupported": self.unsupported[:5]}


def groundedness_score(answer: str, sources: list[str], *, threshold: float = 0.35) -> Groundedness:
    """Score how well `answer` is supported by `sources` (lexical containment)."""
    src_tokens = set()
    for s in sources:
        src_tokens |= _content_tokens(s)
    sentences = [s.strip() for s in _SENT.split(answer or "") if len(s.strip()) > 8]
    if not sentences:
        return Groundedness(score=1.0, supported=0, total=0, unsupported=[])
    if not src_tokens:
        # No evidence at all -> we can't claim grounding; neutral-low.
        return Groundedness(score=0.5, supported=0, total=len(sentences), unsupported=sentences)

    supported = 0
    unsupported: list[str] = []
    for sent in sentences:
        toks = _content_tokens(sent)
        if not toks:
            supported += 1  # no factual content to ground
            continue
        containment = len(toks & src_tokens) / len(toks)
        if containment >= threshold:
            supported += 1
        else:
            unsupported.append(sent)
    return Groundedness(score=supported / len(sentences), supported=supported,
                        total=len(sentences), unsupported=unsupported)
