"""Context Compression Engine (Cognitive Processing Engine v2).

Builds a compact, safe "context pack" for a model: keeps trusted system
instructions strictly separate from untrusted external content, preserves
important facts / open tasks / constraints, removes duplicates, redacts secrets,
and stays within a character budget to prevent context overflow.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.security.prompt_injection import redact_secrets, wrap_untrusted


@dataclass
class ContextPack:
    system: str  # trusted instructions only
    facts: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    memory_summary: str = ""
    untrusted: str = ""  # wrapped external content (never instructions)

    def render(self) -> str:
        """Render to a single prompt string with clear trust boundaries."""
        parts = [self.system]
        if self.constraints:
            parts.append("Constraints:\n" + "\n".join(f"- {c}" for c in self.constraints))
        if self.facts:
            parts.append("Known facts:\n" + "\n".join(f"- {f}" for f in self.facts))
        if self.open_tasks:
            parts.append("Open tasks:\n" + "\n".join(f"- {t}" for t in self.open_tasks))
        if self.memory_summary:
            parts.append("Relevant memory:\n" + self.memory_summary)
        if self.untrusted:
            parts.append(self.untrusted)
        return "\n\n".join(parts)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = " ".join(it.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


class ContextCompressor:
    def __init__(self, budget_chars: int = 6000) -> None:
        self.budget = budget_chars

    def compress(
        self,
        *,
        system: str,
        facts: list[str] | None = None,
        open_tasks: list[str] | None = None,
        constraints: list[str] | None = None,
        memory_summary: str = "",
        untrusted_blocks: list[tuple[str, str]] | None = None,  # (source, content)
    ) -> ContextPack:
        facts = _dedupe([redact_secrets(f) for f in (facts or [])])
        open_tasks = _dedupe(open_tasks or [])
        constraints = _dedupe(constraints or [])

        # Wrap each untrusted block separately; redact secrets first.
        untrusted = ""
        if untrusted_blocks:
            wrapped = [
                wrap_untrusted(redact_secrets(content), source=source)
                for source, content in untrusted_blocks
            ]
            untrusted = "\n\n".join(wrapped)

        pack = ContextPack(
            system=redact_secrets(system), facts=facts, open_tasks=open_tasks,
            constraints=constraints, memory_summary=redact_secrets(memory_summary),
            untrusted=untrusted,
        )
        # Enforce budget by trimming the lowest-priority sections first.
        self._enforce_budget(pack)
        return pack

    def _enforce_budget(self, pack: ContextPack) -> None:
        def total() -> int:
            return len(pack.render())

        # Trim order: untrusted -> memory_summary -> facts -> open_tasks.
        while total() > self.budget and pack.untrusted:
            pack.untrusted = pack.untrusted[: max(0, len(pack.untrusted) - 1000)]
            if len(pack.untrusted) < 200:
                pack.untrusted = ""
        while total() > self.budget and pack.memory_summary:
            pack.memory_summary = pack.memory_summary[: max(0, len(pack.memory_summary) - 500)]
            if len(pack.memory_summary) < 100:
                pack.memory_summary = ""
        while total() > self.budget and pack.facts:
            pack.facts.pop()
        while total() > self.budget and pack.open_tasks:
            pack.open_tasks.pop()
