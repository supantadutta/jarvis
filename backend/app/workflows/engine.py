"""Workflow execution engine (Phase 2).

Runs a WorkflowDef's steps through the assigned agents, honoring the workflow's
approval policy, and writes the output via the permissioned tool layer (so even
workflow actions pass the Permission Guard). Runs are recorded for the dashboard.

Scheduling (cron triggers) is provided by `WorkflowScheduler` as a lightweight
in-process loop; in production this is swapped for Arq/APScheduler.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.agents.base import AgentContext
from app.model_router.modes import Mode
from app.model_router.router import RoutingRequest
from app.workflows.definitions import SEED_WORKFLOWS, WorkflowDef, workflow_public


@dataclass
class WorkflowRunRecord:
    id: str
    workflow_key: str
    status: str = "pending"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    outputs: list[str] = field(default_factory=list)
    step_summaries: list[str] = field(default_factory=list)
    error: str | None = None

    def public(self) -> dict:
        return {
            "id": self.id,
            "workflow_key": self.workflow_key,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outputs": self.outputs,
            "step_summaries": self.step_summaries,
            "error": self.error,
        }


class WorkflowEngine:
    def __init__(self, brain) -> None:
        self.brain = brain
        self._runs: list[WorkflowRunRecord] = []

    @staticmethod
    def find(key: str) -> WorkflowDef | None:
        return next((w for w in SEED_WORKFLOWS if w.key == key), None)

    def runs(self, limit: int = 50) -> list[WorkflowRunRecord]:
        return list(reversed(self._runs[-limit:]))

    def _worker_for(self, wf: WorkflowDef):
        for key in wf.required_agents:
            agent = self.brain.agents.get(key)
            if agent is not None:
                return agent
        return self.brain.supervisor

    async def run(self, key: str) -> WorkflowRunRecord:
        wf = self.find(key)
        run = WorkflowRunRecord(id=uuid.uuid4().hex[:12], workflow_key=key, status="running")
        self._runs.append(run)
        if wf is None:
            run.status = "failed"
            run.error = f"Unknown workflow '{key}'"
            run.finished_at = datetime.now(timezone.utc).isoformat()
            return run

        try:
            # Route a model appropriate to the workflow.
            routing = self.brain.router.route(
                self.brain.registry.enabled(), RoutingRequest(mode=Mode.SINGLE_BEST_MODEL)
            )
            spec = routing.primary or self.brain.registry.enabled()[0]
            provider = self.brain.provider_for(spec)
            worker = self._worker_for(wf)

            collected: list[str] = []
            for step in wf.steps:
                ctx = AgentContext(
                    user_command=f"{wf.name}: {step}",
                    model=spec,
                    provider=provider,
                    services=self.brain.service_bundle(),
                )
                res = await worker.run(ctx)
                run.step_summaries.append(f"{step}: {res.text[:120]}")
                collected.append(f"## {step}\n\n{res.text}")

            # Persist the workflow output via the permissioned tool layer.
            from app.tools.base import ToolContext

            tctx = ToolContext(
                settings=self.brain.settings,
                workspace_root=self.brain.settings.workspace_root,
                services=self.brain.service_bundle(),
                agent_key=worker.key,
                model_key=spec.key,
                user_command=f"workflow:{key}",
            )
            outcome = await self.brain.executor.execute(
                "create_report_markdown",
                {"title": wf.key, "content": "\n\n".join(collected)},
                tctx,
                task_name=f"workflow:{wf.key}",
            )
            if outcome.result.ok and outcome.result.artifacts:
                run.outputs.extend(outcome.result.artifacts)

            run.status = "completed"
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
        finally:
            run.finished_at = datetime.now(timezone.utc).isoformat()
            self.brain.audit.record(
                agent="workflow", tool="workflow_run",
                input_summary=f"workflow:{key}",
                output_summary=f"status={run.status} outputs={len(run.outputs)}",
                risk=wf.risk_level if wf else "low",
                approval_status="auto",
                error=run.error,
            )
        return run


class WorkflowScheduler:
    """Cron-driven scheduler. Phase 2 ships an in-process asyncio loop that ticks
    once a minute and runs due `schedule`-trigger workflows; swap for Arq/
    APScheduler when distributed execution is needed. Each workflow runs at most
    once per matching minute (deduped by last-run minute)."""

    def __init__(self, engine: WorkflowEngine) -> None:
        self.engine = engine
        self._last_run_minute: dict[str, str] = {}
        self._task = None
        self._stop = False

    def scheduled(self) -> list[dict]:
        return [workflow_public(w) for w in SEED_WORKFLOWS if w.trigger == "schedule"]

    def due(self, now: datetime) -> list[str]:
        """Keys of schedule-trigger workflows whose cron matches `now`."""
        from app.workflows.cron import cron_match

        keys: list[str] = []
        for w in SEED_WORKFLOWS:
            if w.trigger != "schedule" or not w.schedule:
                continue
            try:
                if cron_match(w.schedule, now):
                    keys.append(w.key)
            except ValueError:
                continue
        return keys

    async def run_due(self, now: datetime) -> list[str]:
        """Run all due workflows not already run this minute; return ran keys."""
        stamp = now.strftime("%Y-%m-%dT%H:%M")
        ran: list[str] = []
        for key in self.due(now):
            if self._last_run_minute.get(key) == stamp:
                continue
            self._last_run_minute[key] = stamp
            await self.engine.run(key)
            ran.append(key)
        return ran

    async def start(self) -> None:  # pragma: no cover - background loop
        import asyncio

        self._stop = False

        async def loop():
            while not self._stop:
                try:
                    await self.run_due(datetime.now())
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(60)

        self._task = asyncio.create_task(loop())

    async def stop(self) -> None:  # pragma: no cover
        self._stop = True
        if self._task:
            self._task.cancel()
            self._task = None
