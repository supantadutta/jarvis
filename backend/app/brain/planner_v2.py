"""Advanced Planner v2 (Cognitive Processing Engine v2).

Produces a machine-readable, auditable plan as a DAG of nodes with dependencies,
per-step agent/tool/model preference, risk + permission labels, verification
criteria, rollback plans, and approval requirements. Deterministic-first so it is
hermetic and testable; permissions/approvals for tool nodes are resolved from the
real Tool Registry, so the plan is consistent with the Permission Guard.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.brain.analyzer import TaskAnalysis
from app.security.permissions import ALWAYS_APPROVE
from app.tools.base import ToolRegistry


class PlanNode(BaseModel):
    id: str
    description: str
    kind: str = "reason"  # reason | tool
    agent: str = "supervisor"
    tool: str | None = None
    args: dict = Field(default_factory=dict)
    model_preference: str = "any"  # any | reasoning | coding | private | fast
    permission: str = "SAFE_READ"
    risk: str = "low"
    depends_on: list[str] = Field(default_factory=list)
    verification: str = ""
    rollback: str | None = None
    approval_required: bool = False
    complexity: int = 1


class Plan(BaseModel):
    goal: str
    strategy: str = ""
    nodes: list[PlanNode] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def node(self, node_id: str) -> PlanNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def is_dag(self) -> bool:
        """True if dependencies form a valid DAG (no cycles, all refs exist)."""
        ids = {n.id for n in self.nodes}
        if any(d not in ids for n in self.nodes for d in n.depends_on):
            return False
        # Kahn's algorithm.
        indeg = {n.id: 0 for n in self.nodes}
        for n in self.nodes:
            for _ in n.depends_on:
                indeg[n.id] += 1
        ready = [i for i, d in indeg.items() if d == 0]
        seen = 0
        while ready:
            cur = ready.pop()
            seen += 1
            for n in self.nodes:
                if cur in n.depends_on:
                    indeg[n.id] -= 1
                    if indeg[n.id] == 0:
                        ready.append(n.id)
        return seen == len(self.nodes)


# Skill -> (agent, tool, model_preference) for the "gather" stage. Only tools
# whose args the planner can fill deterministically are used here.
_SKILL_NODE = {
    "research": ("research", "web_search", "reasoning"),
    "web": ("research", "web_search", "reasoning"),
    "cybersecurity": ("soc", "build_soc_query", "reasoning"),
}


def _gather_args(tool: str, analysis: TaskAnalysis) -> dict:
    if tool == "web_search":
        return {"query": analysis.intent[:120], "limit": 5}
    if tool == "build_soc_query":
        return {"index": "*"}
    return {}


class AdvancedPlanner:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    def _tool_labels(self, tool: str | None) -> tuple[str, str, bool]:
        """Resolve (permission, risk, approval_required) from the real registry."""
        if not tool:
            return "SAFE_READ", "none", False
        spec = self.tools.get(tool)
        if not spec:
            return "SAFE_READ", "low", False
        approval = (
            spec.requires_approval
            or spec.uses_credential
            or spec.is_irreversible
            or spec.permission in ALWAYS_APPROVE
        )
        return spec.permission.value, spec.risk.value, approval

    def plan(self, analysis: TaskAnalysis, *, strategy: str = "") -> Plan:
        nodes: list[PlanNode] = []
        gather_ids: list[str] = []

        # 1. Gather nodes (one per detected skill that maps to a tool).
        for skill in analysis.required_skills:
            mapping = _SKILL_NODE.get(skill)
            if not mapping:
                continue
            agent, tool, model_pref = mapping
            perm, risk, approval = self._tool_labels(tool)
            nid = f"gather_{skill}"
            nodes.append(PlanNode(
                id=nid, description=f"Gather information using {tool} ({skill}).",
                kind="tool", agent=agent, tool=tool, args=_gather_args(tool, analysis),
                model_preference=model_pref, permission=perm, risk=risk,
                approval_required=approval, verification="tool returned usable, non-empty data",
                rollback=None, complexity=1,
            ))
            gather_ids.append(nid)

        # 2. Reasoning/synthesis node (depends on gather nodes).
        reason_pref = "private" if not analysis.cloud_allowed else (
            "coding" if "coding" in analysis.required_skills else "reasoning")
        nodes.append(PlanNode(
            id="reason", description=f"Reason about the goal: {analysis.intent}",
            kind="reason", agent="supervisor", model_preference=reason_pref,
            permission="SAFE_READ", risk="none", depends_on=gather_ids,
            verification="addresses the user's intent and constraints",
            complexity=analysis.complexity,
        ))

        # 3. Optional output-production node (write a report/note) — low-risk write.
        last = "reason"
        if analysis.output_format in ("report", "markdown") or analysis.background_recommended:
            perm, risk, approval = self._tool_labels("create_report_markdown")
            nodes.append(PlanNode(
                id="produce", description="Produce the output document.",
                kind="tool", agent="file", tool="create_report_markdown",
                args={"title": "result"}, model_preference="any",
                permission=perm, risk=risk, approval_required=approval,
                depends_on=["reason"], rollback="delete the generated file",
                verification="document written and non-empty",
            ))
            last = "produce"

        # 4. Verification node (mandatory for risky/complex/verify tasks).
        if analysis.verifier_mandatory:
            nodes.append(PlanNode(
                id="verify", description="Verify correctness, safety, completeness.",
                kind="reason", agent="verifier", model_preference="reasoning",
                permission="SAFE_READ", risk="none", depends_on=[last],
                verification="verifier passes (no critical issues)",
            ))

        return Plan(goal=analysis.intent, strategy=strategy, nodes=nodes)
