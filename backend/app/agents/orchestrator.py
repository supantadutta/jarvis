"""Orchestrator — runs the multi-AI workflow for a command.

Implements the request lifecycle: classify -> route -> (plan) -> execute by mode
-> verify -> compose -> audit. Modes covered: SINGLE_BEST, FAST, PRIVATE,
VERIFIER, DEEP_WORK, PARALLEL, DEBATE, CASCADE, COST_SAVER, SPECIALIST_TEAM.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import AgentContext, AgentResult
from app.agents.supervisor import Classification
from app.llm.registry import CostType, ModelSpec, TaskType
from app.model_router.modes import MULTI_MODEL_MODES, Mode
from app.model_router.router import CostSetting, RoutingRequest, RoutingResult
from app.services.approvals import ApprovalQueue, ApprovalRequest
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
    attempts: list[str] = field(default_factory=list)  # models tried, in order


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
    # Cascade/cost-saver are explicitly allowed to escalate to cloud (approval
    # gates the paid hop), so they don't impose the default privacy floor.
    if mode == Mode.PRIVATE_MODE:
        privacy_required = 5
    elif mode in (Mode.CASCADE_MODE, Mode.COST_SAVER_MODE):
        privacy_required = 1
    else:
        privacy_required = 2
    return RoutingRequest(
        task_type=tt,
        mode=mode,
        privacy_required=privacy_required,
        min_reasoning=min_reason,
        min_coding=4 if needs_code else 0,
        speed_priority=speed,
        cost_setting=cost,
        needs_tools=False,
        k=3,
    )


class Orchestrator:
    def __init__(self, brain: Brain, *, approval_timeout: float | None = 300.0) -> None:
        self.brain = brain
        self._approval_timeout = approval_timeout

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

        # Feed learned performance into the router (self-evaluation loop).
        brain.router.performance = brain.evaluations.to_router_performance()

        # Route models over the *healthy* enabled set; fall back to enabled if
        # no health info is available (e.g. provider down but still usable).
        req = _routing_request(cls, mode=mode)
        candidates = await brain.registry.available()
        if not candidates:
            candidates = brain.registry.enabled()
        routing: RoutingResult = brain.router.route(candidates, req)
        if not routing.selected:
            routing.selected = candidates[:1]
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
        attempts: list[str] = []
        verifier_info: dict | None = None
        worker = self._pick_worker(team)

        if mode in MULTI_MODEL_MODES:
            for spec in routing.selected:
                ctx = self._ctx(command, spec, private=private, memory_context=memory_context)
                res = await worker.run(ctx)
                candidates.append({"model": spec.key, "text": res.text})
                contributions.append(res)
                attempts.append(spec.key)
        elif mode == Mode.SPECIALIST_TEAM_MODE:
            primary = routing.selected[0]
            specialists = [k for k in team if k not in ("supervisor", "planner", "verifier")]
            for key in specialists or ["supervisor"]:
                agent = brain.agents.get(key, brain.supervisor)
                ctx = self._ctx(command, primary, private=private, memory_context=memory_context)
                res = await agent.run(ctx)
                contributions.append(res)
                attempts.append(f"{key}:{primary.key}")
            candidates.append({"model": primary.key, "text": contributions[-1].text})
        elif mode in (Mode.CASCADE_MODE, Mode.COST_SAVER_MODE):
            best_text, attempts, contributions, verifier_info = await self._cascade(
                command, routing.selected, worker, private, memory_context, mode
            )
            last_model = attempts[-1] if attempts else routing.selected[0].key
            candidates.append({"model": last_model, "text": best_text})
        else:
            spec = routing.selected[0]
            ctx = self._ctx(command, spec, private=private, memory_context=memory_context)
            res = await worker.run(ctx)
            contributions.append(res)
            candidates.append({"model": spec.key, "text": res.text})
            attempts.append(spec.key)

        task.status = TaskStatus.VERIFYING

        # --- pick / merge answer ---
        chosen_index = 0
        vspec = routing.selected[0]
        vctx = self._ctx(command, vspec, private=private)

        if mode == Mode.DEBATE_MODE and len(candidates) > 1:
            chosen_index = await brain.verifier.judge(vctx, command=command, candidates=candidates)

        answer = candidates[chosen_index]["text"] if candidates else ""

        if mode in (Mode.DEEP_WORK_MODE, Mode.VERIFIER_MODE, Mode.DEBATE_MODE):
            verdict = await brain.verifier.verify(vctx, command=command, answer=answer)
            verifier_info = {
                "passed": verdict.passed,
                "score": verdict.score,
                "issues": verdict.issues,
                "summary": verdict.summary,
            }
            # Record the verdict so the router learns which models do well here.
            brain.evaluations.record(
                vspec.key, cls.task_type, passed=verdict.passed, score=verdict.score
            )
            # Supervisor composes a final answer incorporating verifier notes.
            sctx = self._ctx(command, vspec, private=private, memory_context=memory_context)
            answer = await brain.supervisor.compose_final(
                sctx, command=command, contributions=contributions, verdict_summary=verdict.summary
            )

        # --- finalize ---
        task.result = answer
        task.status = TaskStatus.COMPLETED
        task.touch()

        # Write-through persistence (no-op unless enabled on the Brain).
        brain.persist_chat(role="user", content=command, task_id=task.id, source="orchestrator")
        brain.persist_chat(role="assistant", content=answer, task_id=task.id, source="orchestrator")
        brain.persist_task(task)

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
            attempts=attempts,
        )

    def _pick_worker(self, team: list[str]):
        """Choose the primary specialist that produces the answer."""
        for key in team:
            if key not in ("supervisor", "planner", "verifier"):
                return self.brain.agents.get(key, self.brain.supervisor)
        return self.brain.supervisor

    async def _cascade(
        self,
        command: str,
        specs: list[ModelSpec],
        worker,
        private: bool,
        memory_context: str,
        mode: Mode,
    ) -> tuple[str, list[str], list[AgentResult], dict | None]:
        """Try models cheapest/local-first; verify each; stop when it passes.
        In COST_SAVER_MODE, escalating to a PAID model first requires approval."""
        attempts: list[str] = []
        contributions: list[AgentResult] = []
        verifier_info: dict | None = None
        best_text = ""
        for spec in specs:
            if mode == Mode.COST_SAVER_MODE and spec.cost_type == CostType.PAID:
                if not await self._approve_paid(command, spec):
                    break  # keep the best local answer so far
            ctx = self._ctx(command, spec, private=private, memory_context=memory_context)
            res = await worker.run(ctx)
            attempts.append(spec.key)
            contributions.append(res)
            best_text = res.text
            vctx = self._ctx(command, spec, private=private)
            verdict = await self.brain.verifier.verify(vctx, command=command, answer=res.text)
            verifier_info = {
                "passed": verdict.passed,
                "score": verdict.score,
                "issues": verdict.issues,
                "summary": verdict.summary,
            }
            self.brain.evaluations.record(
                spec.key, self.brain.supervisor.classify(command).task_type,
                passed=verdict.passed, score=verdict.score,
            )
            if verdict.passed:
                break
        return best_text, attempts, contributions, verifier_info

    # Modes whose answer comes from a single model can be token-streamed live.
    _STREAMABLE = frozenset({Mode.SINGLE_BEST_MODEL, Mode.FAST_MODE, Mode.PRIVATE_MODE})

    async def stream_answer(self, command: str, *, mode_override: Mode | None = None):
        """Async generator of (event, data) tuples. Single-model modes stream the
        worker model's tokens natively; richer modes fall back to running the full
        orchestration and chunking the final answer."""
        brain = self.brain
        cls = brain.supervisor.classify(command)
        mode = mode_override or cls.mode
        yield ("classified", {"task_type": cls.task_type.value, "mode": mode.value})

        if mode not in self._STREAMABLE:
            result = await self.run(command, mode_override=mode_override)
            yield ("routed", {"models": result.models, "agents": result.agents})
            if result.plan:
                yield ("plan", {"steps": result.plan})
            words = result.answer.split(" ")
            for i in range(0, len(words), 8):
                yield ("token", {"text": " ".join(words[i : i + 8]) + " "})
            yield ("done", {
                "task_id": result.task_id, "verifier": result.verifier,
                "attempts": result.attempts,
                "pending_approvals": result.pending_approvals,
            })
            return

        # --- native single-model token streaming ---
        from app.llm.base import ChatMessage, CompletionRequest, Role, stream_text

        req = _routing_request(cls, mode=mode)
        candidates = await brain.registry.available() or brain.registry.enabled()
        routing = brain.router.route(candidates, req)
        selected = routing.selected or candidates[:1]
        spec = selected[0]
        team = brain.supervisor.select_team(cls)
        task = brain.tasks.create(command, cls.task_type.value, mode.value)
        task.models = [spec.key]
        task.agents = team
        task.status = TaskStatus.RUNNING
        yield ("routed", {"models": [spec.key], "agents": team})

        worker = self._pick_worker(team)
        mem_hits = brain.memory.search(command, limit=3)
        memory_context = "\n".join(f"- {h.item.text}" for h in mem_hits)
        system = worker.system_prompt
        if memory_context:
            system += f"\n\nRelevant memory:\n{memory_context}"
        provider = brain.provider_for(spec)
        creq = CompletionRequest(
            model=spec.model_name,
            messages=[ChatMessage(Role.SYSTEM, system), ChatMessage(Role.USER, command)],
            temperature=0.2,
        )
        acc = ""
        try:
            async for chunk in stream_text(provider, creq):
                acc += chunk
                yield ("token", {"text": chunk})
        except Exception as exc:  # noqa: BLE001
            yield ("error", {"message": str(exc)})

        task.result = acc
        task.status = TaskStatus.COMPLETED
        task.touch()
        brain.persist_chat(role="user", content=command, task_id=task.id, source="stream")
        brain.persist_chat(role="assistant", content=acc, task_id=task.id, source="stream")
        brain.persist_task(task)
        brain.audit.record(
            user_command=command, agent="supervisor", model=spec.key,
            input_summary=command, output_summary=acc, risk="low",
            approval_status="auto", extra={"mode": mode.value, "stream": True},
        )
        yield ("done", {
            "task_id": task.id, "verifier": None, "attempts": [spec.key],
            "pending_approvals": [a.id for a in brain.approvals.pending()],
        })

    async def _approve_paid(self, command: str, spec: ModelSpec) -> bool:
        approval = self.brain.approvals.create(
            ApprovalRequest(
                task_name="cost-saver escalation",
                requested_action=f"Escalate to paid cloud model {spec.key}",
                agent="supervisor",
                model=spec.key,
                tool="llm_call",
                account=spec.provider,
                credential=None,
                risk="medium",
                what_can_change="Sends your prompt to a paid cloud provider (leaves the machine).",
                action_preview=f"Use {spec.display_name} ({spec.cost_type.value}) for: {command[:80]}",
                allow_trust=True,
            )
        )
        resolved = await self.brain.approvals.wait(approval.id, timeout=self._approval_timeout)
        return ApprovalQueue.is_granted(resolved)
