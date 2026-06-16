"""Orchestrator — runs the multi-AI workflow for a command.

Implements the request lifecycle: classify -> route -> (plan) -> execute by mode
-> verify -> compose -> audit. Modes covered: SINGLE_BEST, FAST, PRIVATE,
VERIFIER, DEEP_WORK, PARALLEL, DEBATE, CASCADE, COST_SAVER, SPECIALIST_TEAM.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import AgentContext, AgentResult
from app.agents.supervisor import Classification
from app.llm.registry import ModelSpec, TaskType
from app.model_router.modes import MULTI_MODEL_MODES, Mode
from app.model_router.router import CostSetting, RoutingRequest, RoutingResult
from app.services.container import Brain
from app.services.tasks import TaskStatus, TaskStep


@dataclass
class OrchestratorResult:
    task_id: str
    answer: str
    task_type: str
    mode: str
    models: list[str]
    agents: list[str]
    plan: list[dict] = field(default_factory=list)
    verifier: dict | None = None
    candidates: list[dict] = field(default_factory=list)
    pending_approvals: list[str] = field(default_factory=list)


# Map a task type to routing requirements.
def _routing_request(cls: Classification, *, mode: Mode) -> RoutingRequest:
    tt = cls.task_type
    needs_code = tt in (TaskType.CODING, TaskType.CYBERSECURITY, TaskType.DATA_ANALYSIS)
    cost = CostSetting.PREFER_LOCAL
    if mode in (Mode.PRIVATE_MODE,):
        cost = CostSetting.FREE_ONLY
    elif mode == Mode.DEEP_WORK_MODE:
        cost = CostSetting.ALLOW_PAID
    speed = 5 if mode == Mode.FAST_MODE else 2
    min_reason = 4 if mode == Mode.DEEP_WORK_MODE else (1 if mode == Mode.FAST_MODE else 2)
    return RoutingRequest(
        task_type=tt,
        mode=mode,
        privacy_required=2 if mode != Mode.PRIVATE_MODE else 5,
        min_reasoning=min_reason,
        min_coding=4 if needs_code else 0,
        speed_priority=speed,
        cost_setting=cost,
        needs_tools=False,
        k=3,
    )


class Orchestrator:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    def _ctx(self, command: str, spec: ModelSpec, *, private: bool, memory_context: str = "") -> AgentContext:
        provider = self.brain.provider_for(spec)
        return AgentContext(
            user_command=command,
            model=spec,
            provider=provider,
            memory_context=memory_context,
            services=self.brain.service_bundle(),
            private_mode=private,
        )

    async def run(self, command: str, *, mode_override: Mode | None = None) -> OrchestratorResult:
        brain = self.brain
        cls = brain.supervisor.classify(command)
        mode = mode_override or cls.mode
        private = mode == Mode.PRIVATE_MODE

        # Route models.
        req = _routing_request(cls, mode=mode)
        routing: RoutingResult = brain.router.route(brain.registry.enabled(), req)
        if not routing.selected:
            # Fall back to any enabled model (e.g. mock in tests/local).
            enabled = brain.registry.enabled()
            routing.selected = enabled[:1]
        if not routing.selected:
            raise RuntimeError("No models available to handle the request.")

        team = brain.supervisor.select_team(cls)
        task = brain.tasks.create(command, cls.task_type.value, mode.value)
        task.models = [m.key for m in routing.selected]
        task.agents = team
        task.status = TaskStatus.RUNNING

        # Retrieve memory context (SAFE_READ, auto).
        mem_hits = brain.memory.search(command, limit=3)
        memory_context = "\n".join(f"- {h.item.text}" for h in mem_hits)

        # --- planning (skipped in FAST_MODE for speed) ---
        plan_dicts: list[dict] = []
        if mode != Mode.FAST_MODE:
            primary = routing.selected[0]
            pctx = self._ctx(command, primary, private=private, memory_context=memory_context)
            steps = await brain.planner.plan(pctx)
            task.steps = [
                TaskStep(
                    index=i,
                    description=s.description,
                    permission=s.permission.value,
                    risk=s.risk.value,
                    tool=s.tool,
                    agent="planner",
                )
                for i, s in enumerate(steps)
            ]
            plan_dicts = [
                {"description": s.description, "permission": s.permission.value, "risk": s.risk.value}
                for s in steps
            ]
            task.status = TaskStatus.PLANNING

        # --- execute by mode ---
        candidates: list[dict] = []
        contributions: list[AgentResult] = []
        worker = self._pick_worker(team)

        if mode in MULTI_MODEL_MODES:
            for spec in routing.selected:
                ctx = self._ctx(command, spec, private=private, memory_context=memory_context)
                res = await worker.run(ctx)
                candidates.append({"model": spec.key, "text": res.text})
                contributions.append(res)
        else:
            spec = routing.selected[0]
            ctx = self._ctx(command, spec, private=private, memory_context=memory_context)
            res = await worker.run(ctx)
            contributions.append(res)
            candidates.append({"model": spec.key, "text": res.text})

        task.status = TaskStatus.VERIFYING

        # --- pick / merge answer ---
        verifier_info: dict | None = None
        chosen_index = 0
        vspec = routing.selected[0]
        vctx = self._ctx(command, vspec, private=private)

        if mode == Mode.DEBATE_MODE and len(candidates) > 1:
            chosen_index = await brain.verifier.judge(vctx, command=command, candidates=candidates)

        answer = candidates[chosen_index]["text"]

        if mode in (Mode.DEEP_WORK_MODE, Mode.VERIFIER_MODE, Mode.DEBATE_MODE):
            verdict = await brain.verifier.verify(vctx, command=command, answer=answer)
            verifier_info = {
                "passed": verdict.passed,
                "score": verdict.score,
                "issues": verdict.issues,
                "summary": verdict.summary,
            }
            # Supervisor composes a final answer incorporating verifier notes.
            sctx = self._ctx(command, vspec, private=private, memory_context=memory_context)
            answer = await brain.supervisor.compose_final(
                sctx, command=command, contributions=contributions, verdict_summary=verdict.summary
            )

        # --- finalize ---
        task.result = answer
        task.status = TaskStatus.COMPLETED
        task.touch()

        # Save useful results to memory in deep-work mode.
        if mode == Mode.DEEP_WORK_MODE and verifier_info and verifier_info.get("passed"):
            brain.memory.add(answer, collection="deep_work", source=f"task:{task.id}")

        brain.audit.record(
            user_command=command,
            agent="supervisor",
            model=task.models[0] if task.models else None,
            tool=None,
            input_summary=command,
            output_summary=answer,
            risk="low",
            approval_status="auto",
            extra={"mode": mode.value, "task_type": cls.task_type.value},
        )

        return OrchestratorResult(
            task_id=task.id,
            answer=answer,
            task_type=cls.task_type.value,
            mode=mode.value,
            models=task.models,
            agents=team,
            plan=plan_dicts,
            verifier=verifier_info,
            candidates=candidates if mode in MULTI_MODEL_MODES else [],
            pending_approvals=[a.id for a in brain.approvals.pending()],
        )

    def _pick_worker(self, team: list[str]):
        """Choose the primary specialist that produces the answer."""
        for key in team:
            if key not in ("supervisor", "planner", "verifier"):
                return self.brain.agents.get(key, self.brain.supervisor)
        return self.brain.supervisor
