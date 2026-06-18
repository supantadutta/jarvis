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
    def __init__(
        self, settings: Settings | None = None, *, use_mock: bool = False, persist: bool = False
    ) -> None:
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

        # --- self-evaluation (feeds router performance) ---
        from app.eval.evaluations import EvaluationStore

        self.evaluations = EvaluationStore()

        # --- stateful services ---
        self.memory = self._build_memory()
        self.tasks = TaskStore()
        self.approvals = ApprovalQueue()
        self.audit = AuditLog(sink_path=f"{self.settings.audit_dir}/audit.jsonl")

        # --- live event bus (dashboard timeline) ---
        from app.services.events import EventBus

        self.events = EventBus()
        self.audit.add_listener(self.events.audit_listener())

        # --- security ---
        self.emergency_stop = False
        self.guard = self._build_guard()

        # --- tools ---
        self.tools = ToolRegistry()
        register_builtin_tools(self.tools)
        self.executor = ToolExecutor(self.tools, self.guard, self.approvals, self.audit)

        # --- plugin system (opt-in; off by default) ---
        from app.plugins.loader import PluginManager

        self.plugins = PluginManager(self.tools)

        # --- Phase 2 capabilities (lazy/optional; degrade gracefully) ---
        from app.browser.controller import BrowserController

        self.browser = BrowserController(
            allowed_domains=self.settings.allowed_domains,
            headless=self.settings.browser_headless,
            screenshots_dir=self.settings.screenshots_dir,
        )

        # --- workflows ---
        from app.workflows.engine import WorkflowEngine, WorkflowScheduler

        self.workflows = WorkflowEngine(self)
        self.scheduler = WorkflowScheduler(self.workflows)

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

        # --- write-through persistence (opt-in) ---
        self.persist_enabled = persist
        self._engine = None
        if persist:
            self._setup_persistence()

    def _setup_persistence(self) -> None:
        """Create the DB schema and attach write-through listeners so audit
        entries and approvals land in the database as they happen."""
        from sqlmodel import create_engine

        from app.services import persistence as repo

        url = self.settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args)
        import app.models.tables  # noqa: F401  (register metadata)
        from sqlmodel import SQLModel

        SQLModel.metadata.create_all(self._engine)

        def _on_audit(entry):
            with self._session() as s:
                repo.persist_audit(s, entry)

        def _on_approval(approval):
            with self._session() as s:
                repo.persist_approval(s, approval)

        self.audit.add_listener(_on_audit)
        self.approvals.add_listener(_on_approval)

    def _session(self):
        from sqlmodel import Session

        return Session(self._engine)

    def persist_task(self, task) -> None:
        """Persist a task + its steps if persistence is enabled (no-op otherwise)."""
        if not self.persist_enabled or self._engine is None:
            return
        from app.services import persistence as repo

        with self._session() as s:
            repo.persist_task(s, task)

    def persist_chat(self, *, role: str, content: str, task_id: str | None, source: str) -> None:
        if not self.persist_enabled or self._engine is None:
            return
        from app.services import persistence as repo

        with self._session() as s:
            repo.persist_chat(s, role=role, content=content, task_id=task_id, source=source)

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

    def _build_memory(self):
        """Select the memory backend from settings.vector_backend.

        memory (default) = dependency-free lexical retriever.
        local_vector     = offline embedding (hashing) + cosine index.
        chroma / qdrant  = external vector DB (lazy); falls back to lexical if
                           the dependency/service is unavailable.
        """
        backend = (self.settings.vector_backend or "memory").lower()
        if backend in ("memory", "lexical"):
            return MemoryStore()
        try:
            from app.rag.vector import (
                ChromaVectorBackend,
                LocalVectorBackend,
                QdrantVectorBackend,
                VectorMemoryStore,
            )

            if backend in ("local_vector", "local-vector"):
                return VectorMemoryStore(LocalVectorBackend())
            if backend == "chroma":
                return VectorMemoryStore(ChromaVectorBackend(self.settings.chroma_path))
            if backend == "qdrant":
                return VectorMemoryStore(QdrantVectorBackend(self.settings.qdrant_url))
        except Exception as exc:  # noqa: BLE001 - degrade gracefully to lexical
            import logging

            logging.getLogger("jarvis").warning(
                "Vector backend '%s' unavailable (%s); using lexical memory.", backend, exc
            )
        return MemoryStore()

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
            "browser": self.browser,
        }
