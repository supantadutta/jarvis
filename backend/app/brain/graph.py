"""Multi-Agent Execution Graph (Cognitive Processing Engine v2).

Runs a Plan (DAG) with proper async: independent nodes run in parallel waves,
tool nodes go through the ToolExecutor (so the Permission Guard gates every
action and risky steps pause for approval), reasoning nodes call the routed
model. Supports retry + fallback, per-node timeout, cancellation, partial-result
recovery (dependents of a failed node are skipped), and per-node audit logging.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from app.brain.planner_v2 import Plan, PlanNode
from app.llm.base import ChatMessage, CompletionRequest, Role
from app.tools.base import ToolContext


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class NodeResult:
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    output: str = ""
    decision: str = ""
    approval_id: str | None = None
    retries: int = 0
    latency_ms: int = 0
    error: str | None = None


@dataclass
class GraphRunResult:
    goal: str
    results: dict[str, NodeResult] = field(default_factory=dict)
    final: str = ""
    completed: bool = False
    cancelled: bool = False

    def public(self) -> dict:
        return {
            "goal": self.goal, "final": self.final, "completed": self.completed,
            "cancelled": self.cancelled,
            "nodes": [
                {"node_id": r.node_id, "status": r.status.value, "decision": r.decision,
                 "approval_id": r.approval_id, "retries": r.retries,
                 "latency_ms": r.latency_ms, "error": r.error,
                 "output": r.output[:400]}
                for r in self.results.values()
            ],
        }


class GraphExecutor:
    def __init__(self, brain, *, node_timeout: float = 30.0, max_retries: int = 1,
                 private_mode: bool = False) -> None:
        self.brain = brain
        self.node_timeout = node_timeout
        self.max_retries = max_retries
        self.private_mode = private_mode
        self._cancel = asyncio.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _pick_provider(self, preference: str):
        from app.model_router.modes import Mode
        from app.model_router.router import RoutingRequest

        mode = Mode.PRIVATE_MODE if (preference == "private" or self.private_mode) else \
            Mode.SINGLE_BEST_MODEL
        req = RoutingRequest(mode=mode,
                             min_reasoning=4 if preference == "reasoning" else 0,
                             min_coding=4 if preference == "coding" else 0)
        routing = self.brain.router.route(
            self.brain.registry.enabled() or self.brain.registry.all(), req)
        spec = routing.primary or (self.brain.registry.enabled() or
                                   self.brain.registry.all() or [None])[0]
        return spec, (self.brain.provider_for(spec) if spec else None)

    async def _run_reason(self, node: PlanNode, context: str) -> NodeResult:
        spec, provider = self._pick_provider(node.model_preference)
        r = NodeResult(node_id=node.id)
        if provider is None or spec is None:
            r.status, r.error = NodeStatus.FAILED, "no model"
            return r
        prompt = f"{node.description}\n\nContext so far:\n{context}".strip()
        resp = await provider.complete(CompletionRequest(
            model=spec.model_name,
            messages=[ChatMessage(Role.SYSTEM, f"You are the {node.agent} agent."),
                      ChatMessage(Role.USER, prompt)],
            temperature=0.2))
        r.output, r.decision, r.status = resp.text, "auto", NodeStatus.COMPLETED
        return r

    async def _run_tool(self, node: PlanNode, goal: str) -> NodeResult:
        r = NodeResult(node_id=node.id)
        ctx = ToolContext(
            settings=self.brain.settings, workspace_root=self.brain.settings.workspace_root,
            services=self.brain.service_bundle(), agent_key=node.agent,
            user_command=goal, private_mode=self.private_mode)
        outcome = await self.brain.executor.execute(node.tool, node.args, ctx,
                                                    task_name=f"graph:{node.id}")
        r.decision = outcome.decision.value
        r.approval_id = outcome.approval_id
        if outcome.result.ok:
            r.output = outcome.result.summary or str(outcome.result.output)
            r.status = NodeStatus.COMPLETED
        else:
            r.error = outcome.result.error
            r.status = NodeStatus.FAILED
        return r

    async def _execute_node(self, node: PlanNode, context: str, goal: str) -> NodeResult:
        start = time.perf_counter()
        attempt = 0
        last: NodeResult | None = None
        while attempt <= self.max_retries:
            if self._cancel.is_set():
                last = NodeResult(node_id=node.id, status=NodeStatus.CANCELLED)
                break
            try:
                runner = self._run_tool(node, goal) if node.kind == "tool" \
                    else self._run_reason(node, context)
                last = await asyncio.wait_for(runner, timeout=self.node_timeout)
            except asyncio.TimeoutError:
                last = NodeResult(node_id=node.id, status=NodeStatus.FAILED,
                                  error=f"timeout after {self.node_timeout}s")
            except Exception as exc:  # noqa: BLE001
                last = NodeResult(node_id=node.id, status=NodeStatus.FAILED, error=str(exc))
            last.retries = attempt
            if last.status == NodeStatus.COMPLETED:
                break
            # Don't retry an approval/denied decision.
            if last.decision in ("requires_approval", "deny"):
                break
            attempt += 1
        last.latency_ms = int((time.perf_counter() - start) * 1000)
        self.brain.audit.record(
            agent=node.agent, model=None, tool=node.tool,
            input_summary=node.description, output_summary=last.output or (last.error or ""),
            risk=node.risk, approval_status=last.decision or "auto", error=last.error)
        return last

    async def run(self, plan: Plan) -> GraphRunResult:
        result = GraphRunResult(goal=plan.goal)
        for n in plan.nodes:
            result.results[n.id] = NodeResult(node_id=n.id)
        if not plan.is_dag():
            result.final = "Invalid plan (not a DAG)."
            return result

        done: set[str] = set()
        failed: set[str] = set()
        outputs: dict[str, str] = {}

        while len(done) + len(failed) < len(plan.nodes):
            if self._cancel.is_set():
                result.cancelled = True
                break
            # Ready = not done/failed, all deps done; skip if any dep failed.
            ready: list[PlanNode] = []
            for n in plan.nodes:
                if n.id in done or n.id in failed:
                    continue
                if any(d in failed for d in n.depends_on):
                    result.results[n.id].status = NodeStatus.SKIPPED
                    failed.add(n.id)
                    continue
                if all(d in done for d in n.depends_on):
                    ready.append(n)
            if not ready:
                break  # no progress (e.g. all remaining blocked by failures)

            # Build per-node context from completed dependencies + run in parallel.
            async def _go(node: PlanNode) -> NodeResult:
                ctx = "\n".join(f"[{d}] {outputs.get(d, '')}" for d in node.depends_on)
                return await self._execute_node(node, ctx, plan.goal)

            wave = await asyncio.gather(*[_go(n) for n in ready])
            for nres in wave:
                result.results[nres.node_id] = nres
                if nres.status == NodeStatus.COMPLETED:
                    done.add(nres.node_id)
                    outputs[nres.node_id] = nres.output
                else:
                    failed.add(nres.node_id)

        # Final answer = output of the last completed node (verify/produce/reason).
        for nid in reversed([n.id for n in plan.nodes]):
            if result.results[nid].status == NodeStatus.COMPLETED:
                result.final = outputs.get(nid, "")
                break
        result.completed = not failed and not result.cancelled
        return result
