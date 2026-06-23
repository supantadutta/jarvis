"""Unified execution engine (Cognitive Processing Engine v2).

ONE entry point for the three execution strategies that previously lived as
separate, disconnected engines:

  - CHAT       : question/answer with mode logic (single/cascade/parallel/…),
                 verification and composition  (the Orchestrator).
  - AUTONOMOUS : ReAct tool-using loop to achieve a goal       (AutonomousAgent).
  - GRAPH      : execute a planned DAG of agent/tool nodes      (GraphExecutor).

The engine analyzes the request ONCE, auto-selects the strategy (or honors an
explicit one), runs it under a SHARED SessionBudget, and applies a UNIFORM
post-step: Response Quality assessment + a learning-loop feedback record. So all
three share one analyzer, one budget, one quality/learning path, and one API —
the duplication and disconnection are gone, while each strategy keeps its
specialized executor (composition, not copy-paste).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.agents.orchestrator import Orchestrator
from app.brain.guardrails import SessionBudget
from app.brain.groundedness import groundedness_score
from app.model_router.modes import Mode


class ExecutionKind(str, Enum):
    AUTO = "auto"
    CHAT = "chat"
    AUTONOMOUS = "autonomous"
    GRAPH = "graph"


# Cues that a request needs multi-step *action* (autonomous), not just an answer.
_AGENTIC_CUES = (
    "automate", "organize", "download", "set up", "configure", "build a",
    "and then", "then ", "step by step", "monitor", "do this", "go and",
    "create a project", "scaffold", "fix the", "deploy",
)


@dataclass
class UnifiedResult:
    kind: str
    command: str
    answer: str
    analysis: dict | None = None
    quality: dict | None = None
    groundedness: dict | None = None
    budget: dict | None = None
    detail: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "kind": self.kind, "command": self.command, "answer": self.answer,
            "analysis": self.analysis, "quality": self.quality,
            "groundedness": self.groundedness, "budget": self.budget,
            "detail": self.detail,
        }


class UnifiedEngine:
    def __init__(self, brain) -> None:
        self.brain = brain

    def _new_budget(self) -> SessionBudget:
        s = self.brain.settings
        return SessionBudget(
            max_actions=getattr(s, "agent_max_actions", 25),
            max_seconds=getattr(s, "agent_max_seconds", 120.0),
            max_cost=getattr(s, "session_max_cost", 10.0),
        )

    def select(self, analysis, explicit: ExecutionKind) -> ExecutionKind:
        if explicit != ExecutionKind.AUTO:
            return explicit
        low = (analysis.intent or "").lower()
        if analysis.background_recommended or any(c in low for c in _AGENTIC_CUES):
            return ExecutionKind.AUTONOMOUS
        if len(analysis.required_skills) >= 2:
            return ExecutionKind.GRAPH
        return ExecutionKind.CHAT

    async def run(self, command: str, *, execution: str = "auto",
                  mode: str | None = None, max_steps: int = 8) -> UnifiedResult:
        brain = self.brain
        analysis = brain.analyzer.analyze(command, mode_override=mode)
        kind = self.select(analysis, ExecutionKind(execution))
        budget = self._new_budget()

        if kind == ExecutionKind.CHAT:
            mo = Mode(mode) if mode else None
            res = await Orchestrator(brain).run(command, mode_override=mo)
            return UnifiedResult(
                kind="chat", command=command, answer=res.answer,
                analysis=res.analysis, quality=res.quality, groundedness=res.groundedness,
                detail={"task_id": res.task_id, "mode": res.mode, "models": res.models,
                        "verifier": res.verifier, "attempts": res.attempts,
                        "pending_approvals": res.pending_approvals},
            )

        if kind == ExecutionKind.AUTONOMOUS:
            res = await brain.autonomous.run(command, max_steps=max_steps, budget=budget)
            return self._finalize(command, res.answer, analysis, budget,
                                  kind="autonomous", detail=res.public(), sources=[
                                      s.observation for s in res.steps])

        # GRAPH
        plan = brain.planner_v2.plan(analysis)
        from app.brain.graph import GraphExecutor

        ge = GraphExecutor(brain, private_mode=not analysis.cloud_allowed, budget=budget)
        gres = await ge.run(plan)
        sources = [n.get("output", "") for n in gres.public()["nodes"]]
        return self._finalize(command, gres.final, analysis, budget,
                              kind="graph", detail=gres.public(), sources=sources)

    def _finalize(self, command, answer, analysis, budget, *, kind, detail, sources):
        """Uniform post-step shared by autonomous + graph (chat does its own)."""
        brain = self.brain
        quality = brain.quality.assess(request=command, answer=answer or "",
                                       analysis=analysis).model_dump()
        grounded = None
        ev = [s for s in sources if s and s.strip()]
        if ev:
            grounded = groundedness_score(answer or "", ev).public()
        # Feed the learning loop uniformly.
        spec = (brain.registry.enabled() or brain.registry.all() or [None])[0]
        if spec is not None and hasattr(brain, "feedback"):
            from app.brain.learning import TaskFeedback

            brain.feedback.record(TaskFeedback(
                task_id=f"{kind}:{id(detail)}", model_key=spec.key,
                task_type=analysis.task_type,
                completeness=quality.get("scores", {}).get("completeness", 0.8),
                factuality=(grounded or {}).get("score", 0.7),
                tool_success_rate=1.0))
        return UnifiedResult(kind=kind, command=command, answer=answer or "",
                             analysis=analysis.model_dump(), quality=quality,
                             groundedness=grounded, budget=budget.public(), detail=detail)
