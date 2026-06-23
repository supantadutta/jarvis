"""Agent base classes and shared context."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.base import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    Role,
)
from app.llm.registry import ModelSpec, TaskType
from app.security.permissions import PermissionLevel


@dataclass
class AgentContext:
    user_command: str
    model: ModelSpec
    provider: LLMProvider
    memory_context: str = ""
    services: dict = field(default_factory=dict)
    private_mode: bool = False
    cache: object | None = None  # optional ResponseCache (local-only, speeds repeats)


@dataclass
class AgentResult:
    agent: str
    text: str
    model: str
    confidence: float = 0.7
    citations: list[str] = field(default_factory=list)
    raw: CompletionResponse | None = None


class BaseAgent:
    key: str = "base"
    display_name: str = "Base Agent"
    default_task_type: TaskType = TaskType.DAILY_ASSISTANT
    allowed_permissions: set[PermissionLevel] = {PermissionLevel.SAFE_READ}
    system_prompt: str = "You are a helpful, careful assistant."

    async def _ask(
        self,
        ctx: AgentContext,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        extra_system: str | None = None,
    ) -> CompletionResponse:
        system = self.system_prompt
        if extra_system:
            system += "\n" + extra_system
        if ctx.memory_context:
            system += f"\n\nRelevant memory:\n{ctx.memory_context}"
        messages = [
            ChatMessage(role=Role.SYSTEM, content=system),
            ChatMessage(role=Role.USER, content=prompt),
        ]
        req = CompletionRequest(
            model=ctx.model.model_name,
            messages=messages,
            temperature=temperature,
            json_mode=json_mode,
        )
        if ctx.cache is not None:
            from app.brain.performance import cached_complete

            return await cached_complete(ctx.provider, req, ctx.cache)
        return await ctx.provider.complete(req)

    async def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - overridden
        resp = await self._ask(ctx, ctx.user_command)
        return AgentResult(agent=self.key, text=resp.text, model=resp.model, raw=resp)
