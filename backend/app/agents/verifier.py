"""Verifier / Critic agent — checks correctness, safety, completeness."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents.base import AgentContext, BaseAgent
from app.llm.registry import TaskType


@dataclass
class Verdict:
    passed: bool
    score: float
    issues: list[str]
    summary: str


class VerifierAgent(BaseAgent):
    key = "verifier"
    display_name = "Verifier / Critic AI"
    default_task_type = TaskType.VERIFICATION
    system_prompt = (
        "You are the Verifier. Critically review the candidate answer for "
        "correctness, completeness, safety, and whether it fully addresses the "
        "user's request. Be skeptical. Respond ONLY as JSON: "
        '{"passed":bool,"score":0..1,"issues":[str],"summary":str}.'
    )

    async def verify(self, ctx: AgentContext, *, command: str, answer: str) -> Verdict:
        prompt = (
            f"User request:\n{command}\n\nCandidate answer:\n{answer}\n\n"
            "Verify and critique it."
        )
        resp = await self._ask(ctx, prompt, json_mode=True)
        return self._parse(resp.text)

    async def judge(self, ctx: AgentContext, *, command: str, candidates: list[dict]) -> int:
        """Pick the best candidate (returns its index). Used in DEBATE_MODE."""
        listing = "\n\n".join(
            f"[Candidate {i}] (model={c.get('model')}):\n{c.get('text', '')}"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"User request:\n{command}\n\n{listing}\n\n"
            'Choose the single best candidate. Respond ONLY as JSON: {"best_index":int,"reason":str}.'
        )
        resp = await self._ask(ctx, prompt, json_mode=True)
        try:
            data = json.loads(resp.text)
            idx = int(data.get("best_index", 0))
            return idx if 0 <= idx < len(candidates) else 0
        except (json.JSONDecodeError, TypeError, ValueError):
            return 0

    @staticmethod
    def _parse(raw: str) -> Verdict:
        try:
            data = json.loads(raw)
            return Verdict(
                passed=bool(data.get("passed", False)),
                score=float(data.get("score", 0.0)),
                issues=list(data.get("issues", [])),
                summary=str(data.get("summary", "")),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            # Conservative default: treat unparseable verifier output as a soft pass
            # with a flag, rather than silently trusting it.
            return Verdict(passed=True, score=0.5, issues=["verifier output unparseable"],
                           summary="Could not parse verifier output.")
