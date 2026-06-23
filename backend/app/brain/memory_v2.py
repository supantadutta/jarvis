"""Layered memory architecture (Cognitive Processing Engine v2).

Sits on top of the existing MemoryStore/VectorMemoryStore (one collection per
layer), adding scoped, scored retrieval and summarization:

  working    - scratchpad for the current task (ephemeral)
  episodic   - past user tasks and outcomes
  semantic   - general facts / learned knowledge (vector search)
  procedural - reusable workflows / how-to
  preference - user style and recurring instructions
  soc        - defensive detection-engineering knowledge

Retrieval is scoped by privacy (high-privacy items are withheld when the result
will be sent to a cloud model), and scored by relevance + freshness + source
trust + task-type match. Summarization prevents context overflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

LAYERS = ("working", "episodic", "semantic", "procedural", "preference", "soc")

# Trust weight by source prefix (untrusted web is trusted less than the user).
_TRUST = {"user": 1.0, "task": 0.9, "workflow": 0.9, "web-research": 0.5, "web": 0.4}


def _trust_of(source: str | None) -> float:
    if not source:
        return 0.6
    for prefix, w in _TRUST.items():
        if source.startswith(prefix):
            return w
    return 0.6


def _freshness(created_at: str | None) -> float:
    if not created_at:
        return 0.5
    try:
        dt = datetime.fromisoformat(created_at)
    except ValueError:
        return 0.5
    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    # 1.0 today -> ~0.5 at ~30 days -> floors at 0.2.
    return max(0.2, 1.0 / (1.0 + age_days / 30.0))


@dataclass
class ScoredMemory:
    text: str
    layer: str
    source: str | None
    score: float
    relevance: float
    freshness: float
    trust: float
    privacy: int


class LayeredMemory:
    def __init__(self, store) -> None:
        self.store = store  # MemoryStore or VectorMemoryStore

    def remember(self, layer: str, text: str, *, source: str | None = None,
                 privacy: int = 1, task_type: str | None = None,
                 metadata: dict | None = None):
        meta = dict(metadata or {})
        meta.update({"privacy": privacy, "task_type": task_type})
        coll = layer if layer in LAYERS else "semantic"
        return self.store.add(text, collection=coll, source=source, metadata=meta)

    def recall(self, query: str, *, layers: list[str] | None = None, limit: int = 5,
               for_cloud: bool = False, task_type: str | None = None,
               max_privacy_for_cloud: int = 3) -> list[ScoredMemory]:
        layers = [ly for ly in (layers or LAYERS) if ly in LAYERS]
        scored: list[ScoredMemory] = []
        for layer in layers:
            for hit in self.store.search(query, collection=layer, limit=limit * 2):
                meta = hit.item.metadata or {}
                privacy = int(meta.get("privacy", 1))
                # Privacy scoping: withhold sensitive memory from cloud models.
                if for_cloud and privacy >= max_privacy_for_cloud:
                    continue
                relevance = float(hit.score)
                fresh = _freshness(hit.item.created_at)
                trust = _trust_of(hit.item.source)
                tt_bonus = 0.1 if (task_type and meta.get("task_type") == task_type) else 0.0
                composite = round(
                    0.55 * relevance + 0.2 * fresh + 0.2 * trust + tt_bonus, 4)
                scored.append(ScoredMemory(
                    text=hit.item.text, layer=layer, source=hit.item.source,
                    score=composite, relevance=relevance, freshness=fresh,
                    trust=trust, privacy=privacy))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:limit]

    def summarize(self, query: str, *, layers: list[str] | None = None,
                  for_cloud: bool = False, budget_chars: int = 1200,
                  limit: int = 8) -> str:
        """Compact, scored recall rendered as a bounded context block."""
        hits = self.recall(query, layers=layers, limit=limit, for_cloud=for_cloud)
        out, used = [], 0
        for h in hits:
            line = f"- ({h.layer}, score {h.score}) {h.text.strip()}"
            if used + len(line) > budget_chars:
                break
            out.append(line)
            used += len(line)
        return "\n".join(out)

    def stats(self) -> dict:
        cols = self.store.collections()
        return {ly: cols.get(ly, 0) for ly in LAYERS}
