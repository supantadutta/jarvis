"""Planner agent — decomposes a task into risk-labelled steps."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.llm.registry import TaskType
from app.security.permissions import PermissionLevel, RiskLevel


@dataclass
class PlanStep:
    description: str
    permission: PermissionLevel
    risk: RiskLevel
    tool: str | None = None
    agent: str | None = None


class PlannerAgent(BaseAgent):
    key = "planner"
    display_name = "Planner AI"
    default_task_type = TaskType.PLANNING
    system_prompt = (
        "You are the Planner. Break the user's request into a short ordered list "
        "of concrete steps. For each step choose the least-privilege permission "
        "level and a risk level. Respond ONLY as JSON: "
        '{"steps":[{"description":str,"permission":str,"risk":str,"tool":str|null}]}. '
        "Permission must be one of: SAFE_READ, LOW_RISK_WRITE, BROWSER_READ, "
        "BROWSER_WRITE, DESKTOP_CONTROL, TERMINAL_READ, TERMINAL_WRITE, "
        "CREDENTIAL_ACCESS, NETWORK_ACCESS, HIGH_RISK. Risk: none|low|medium|high|critical."
    )

    async def plan(self, ctx: AgentContext) -> list[PlanStep]:
        resp = await self._ask(ctx, f"Plan this task: {ctx.user_command}", json_mode=True)
        steps = self._parse(resp.text)
        if not steps:
            steps = [PlanStep("Answer the request directly.", PermissionLevel.SAFE_READ, RiskLevel.LOW)]
        return steps

    async def run(self, ctx: AgentContext) -> AgentResult:
        steps = await self.plan(ctx)
        text = "\n".join(
            f"{i + 1}. [{s.permission.value}/{s.risk.value}] {s.description}"
            for i, s in enumerate(steps)
        )
        return AgentResult(agent=self.key, text=text, model=ctx.model.model_name, confidence=0.8)

    @staticmethod
    def _parse(raw: str) -> list[PlanStep]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        out: list[PlanStep] = []
        for item in data.get("steps", []):
            try:
                perm = PermissionLevel(item.get("permission", "SAFE_READ"))
            except ValueError:
                perm = PermissionLevel.SAFE_READ
            try:
                risk = RiskLevel(item.get("risk", "low"))
            except ValueError:
                risk = RiskLevel.LOW
            out.append(
                PlanStep(
                    description=str(item.get("description", "")),
                    permission=perm,
                    risk=risk,
                    tool=item.get("tool"),
                )
            )
        return out
