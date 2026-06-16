"""Composition root — the "Jarvis Brain".

Wires together the registry, router, providers, agents, tool executor, and the
stateful services. Built once at startup (and freshly in tests). Keeps all
shared state in one place so the API layer stays thin.
"""
from __future__ import annotations

from app.agents.planner import PlannerAgent
from app.agents.specialists import SPECIALIST_AGENTS
from app.agents.supervisor import SupervisorAgent
from app.agents.verifier import VerifierAgent
from app.audit.logger import AuditLog
from app.config import Settings, get_settings
from app.llm.base import LLMProvider
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.registry import ModelRegistry, ModelSpec
from app.model_router.router import ModelRouter
from app.rag.memory import MemoryStore
from app.security.permissions import PermissionGuard, PermissionPolicy
from app.services.approvals import ApprovalQueue
from app.services.tasks import TaskStore
from app.tools.base import ToolRegistry
from app.tools.builtin.builtin import register_builtin_tools
from app.tools.executor import ToolExecutor


class Brain:
    def __init__(self, settings: Settings | None = None, *, use_mock: bool = False) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()

        # --- model registry + providers ---
        self.registry = ModelRegistry()
        self.providers: dict[str, LLMProvider] = {}
        self._mock = MockProvider()
        if use_mock:
            # Bind every provider slot to the mock so the whole graph runs offline.
            for name in ("ollama", "openai", "anthropic", "google", "groq",
                         "openrouter", "openai_compatible", "mock"):
                self.providers[name] = self._mock
                self.registry.bind_provider(name, self._mock)
            for spec in self.registry.all():
                spec.enabled = True
        else:
            ollama = OllamaProvider(self.settings.ollama_base_url)
            self.providers["ollama"] = ollama
            self.registry.bind_provider("ollama", ollama)
            self._bind_cloud_providers()
            # Mock always available as a safety net for local/test usage.
            self.providers["mock"] = self._mock
            self.registry.bind_provider("mock", self._mock)

        # --- router ---
        self.router = ModelRouter()

        # --- stateful services ---
        self.memory = MemoryStore()
        self.tasks = TaskStore()
        self.approvals = ApprovalQueue()
        self.audit = AuditLog(sink_path=f"{self.settings.audit_dir}/audit.jsonl")

        # --- security ---
        self.emergency_stop = False
        self.guard = self._build_guard()

        # --- tools ---
        self.tools = ToolRegistry()
        register_builtin_tools(self.tools)
        self.executor = ToolExecutor(self.tools, self.guard, self.approvals, self.audit)

        # --- agents ---
        self.supervisor = SupervisorAgent()
        self.planner = PlannerAgent()
        self.verifier = VerifierAgent()
        self.specialists = SPECIALIST_AGENTS
        self.agents = {
            "supervisor": self.supervisor,
            "planner": self.planner,
            "verifier": self.verifier,
            **self.specialists,
        }

    def _bind_cloud_providers(self) -> None:
        from app.llm.cloud_providers import (
            AnthropicProvider,
            GeminiProvider,
            OpenAICompatibleProvider,
        )

        s = self.settings
        if s.openai_api_key:
            p = OpenAICompatibleProvider(
                name="openai", base_url="https://api.openai.com/v1", api_key=s.openai_api_key
            )
            self.providers["openai"] = p
            self.registry.bind_provider("openai", p)
            self._enable_provider_models("openai")
        if s.groq_api_key:
            p = OpenAICompatibleProvider(
                name="groq", base_url="https://api.groq.com/openai/v1", api_key=s.groq_api_key
            )
            self.providers["groq"] = p
            self.registry.bind_provider("groq", p)
            self._enable_provider_models("groq")
        if s.openrouter_api_key:
            p = OpenAICompatibleProvider(
                name="openrouter", base_url="https://openrouter.ai/api/v1",
                api_key=s.openrouter_api_key,
            )
            self.providers["openrouter"] = p
            self.registry.bind_provider("openrouter", p)
            self._enable_provider_models("openrouter")
        if s.openai_compatible_base_url:
            p = OpenAICompatibleProvider(
                name="openai_compatible", base_url=s.openai_compatible_base_url, api_key=None
            )
            self.providers["openai_compatible"] = p
            self.registry.bind_provider("openai_compatible", p)
        if s.anthropic_api_key:
            p = AnthropicProvider(s.anthropic_api_key)
            self.providers["anthropic"] = p
            self.registry.bind_provider("anthropic", p)
            self._enable_provider_models("anthropic")
        if s.google_api_key:
            p = GeminiProvider(s.google_api_key)
            self.providers["google"] = p
            self.registry.bind_provider("google", p)
            self._enable_provider_models("google")

    def _enable_provider_models(self, provider: str) -> None:
        for spec in self.registry.all():
            if spec.provider == provider:
                spec.enabled = True

    def _build_guard(self) -> PermissionGuard:
        s = self.settings
        return PermissionGuard(
            PermissionPolicy(
                allow_low_risk_write=s.allow_low_risk_write,
                trusted_terminal_read=s.trusted_terminal_read,
                allow_network=s.allow_network,
            ),
            allowed_paths=s.allowed_paths,
            allowed_domains=s.allowed_domains,
            command_allowlist=s.command_allowlist,
            command_blocklist=s.command_blocklist,
            emergency_stop=self.emergency_stop,
        )

    def set_emergency_stop(self, engaged: bool) -> None:
        self.emergency_stop = engaged
        self.guard.emergency_stop = engaged

    def provider_for(self, spec: ModelSpec) -> LLMProvider | None:
        return self.providers.get(spec.provider) or self.providers.get("mock")

    def service_bundle(self) -> dict:
        return {
            "memory": self.memory,
            "tasks": self.tasks,
            "approvals": self.approvals,
            "audit": self.audit,
        }
