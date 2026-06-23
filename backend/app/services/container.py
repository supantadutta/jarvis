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
        self._use_mock = use_mock
        self._provider_config: dict[str, dict] = {}
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
        from app.tools.builtin.web import register_web_tools

        register_web_tools(self.tools)
        self.executor = ToolExecutor(self.tools, self.guard, self.approvals, self.audit)

        # --- self-learning (web research -> memory) ---
        from app.services.learner import SelfLearner

        self.learner = SelfLearner(self)

        # --- autonomous agent loop (the "do anything" engine) ---
        from app.agents.autonomous import AutonomousAgent

        self.autonomous = AutonomousAgent(self)

        # --- Cognitive Processing Engine v2 (additive brain upgrade) ---
        from app.brain.analyzer import CognitiveTaskAnalyzer
        from app.brain.context import ContextCompressor
        from app.brain.learning import FeedbackLoop
        from app.brain.memory_v2 import LayeredMemory
        from app.brain.performance import ResourceMonitor, ResponseCache
        from app.brain.planner_v2 import AdvancedPlanner
        from app.brain.quality import QualityEngine
        from app.brain.router_v2 import BrainRouter

        self.analyzer = CognitiveTaskAnalyzer()
        self.brain_router = BrainRouter(self.router)
        self.planner_v2 = AdvancedPlanner(self.tools)
        self.layered_memory = LayeredMemory(self.memory)
        self.context_compressor = ContextCompressor()
        self.quality = QualityEngine()
        self.response_cache = ResponseCache()
        self.resource_monitor = ResourceMonitor()
        self.feedback = FeedbackLoop(self.evaluations)
        self.graph_runs: dict[str, dict] = {}  # task_id -> GraphRunResult.public()
        from app.brain.queue import ProcessingQueue

        self.processing_queue = ProcessingQueue(concurrency=2)

        # The single unified execution engine (chat/autonomous/graph strategies).
        from app.brain.engine import UnifiedEngine

        self.engine = UnifiedEngine(self)

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

        # --- credentials + encrypted vault (model API keys etc. at rest) ---
        from app.security.credentials import CredentialManager, NullVault

        vault = NullVault()
        if self.settings.vault_key:
            try:
                from app.security.credentials import FernetVault

                vault = FernetVault(self.settings.vault_key,
                                    store_path=f"{self.settings.chroma_path}/vault.json")
            except Exception as exc:  # noqa: BLE001 - degrade to in-memory only
                import logging

                logging.getLogger("jarvis").warning("Vault disabled (%s).", exc)
        self.vault = vault
        self.credentials = CredentialManager(vault)

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
            from app.rag.embeddings import build_embedder
            from app.rag.vector import (
                ChromaVectorBackend,
                LocalVectorBackend,
                QdrantVectorBackend,
                VectorMemoryStore,
            )

            # Real (or offline-hashing) embeddings power the vector store.
            embedder = build_embedder(
                provider=self.settings.embedding_provider,
                base_url=self.settings.ollama_base_url,
                model=self.settings.embedding_model)

            def _embed(text: str) -> list[float]:
                return embedder.embed(text)

            if backend in ("local_vector", "local-vector"):
                return VectorMemoryStore(LocalVectorBackend(), embed=_embed)
            if backend == "chroma":
                return VectorMemoryStore(ChromaVectorBackend(self.settings.chroma_path), embed=_embed)
            if backend == "qdrant":
                return VectorMemoryStore(QdrantVectorBackend(self.settings.qdrant_url), embed=_embed)
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

    # Runtime-mutable, NON-SECRET policy toggles. Secrets are never settable here.
    _MUTABLE_POLICY = {
        "allow_low_risk_write", "trusted_terminal_read", "allow_network",
        "max_cascade_attempts", "default_mode",
    }

    def apply_policy_update(self, updates: dict) -> dict:
        """Apply safe policy changes and rebuild the guard. Returns applied keys."""
        applied: dict = {}
        for key, value in updates.items():
            if key not in self._MUTABLE_POLICY:
                continue
            setattr(self.settings, key, value)
            applied[key] = value
        if applied:
            # Rebuild the guard from the new policy and re-point the executor.
            self.guard = self._build_guard()
            self.guard.emergency_stop = self.emergency_stop
            self.executor.guard = self.guard
        return applied

    def provider_for(self, spec: ModelSpec) -> LLMProvider | None:
        return self.providers.get(spec.provider) or self.providers.get("mock")

    # --- runtime model/provider management ("connect any model" from the UI) ---
    def add_model_source(
        self,
        *,
        provider: str,
        model_name: str,
        display_name: str | None = None,
        kind: str = "openai_compatible",
        base_url: str | None = None,
        api_key: str | None = None,
        cost_type: str = "paid",
        privacy_level: int = 1,
        reasoning_level: int = 4,
        coding_level: int = 4,
        speed_level: int = 3,
        max_context: int = 32768,
        vision_support: bool = False,
        tool_calling_support: bool = True,
        task_affinity: list[str] | None = None,
    ) -> ModelSpec:
        """Register + bind a model from ANY provider at runtime (no code edits)."""
        from app.llm.factory import build_provider
        from app.llm.registry import CostType, ModelSpec, TaskType

        if provider not in self.providers:
            if self._use_mock:
                self.providers[provider] = self._mock
            else:
                self.providers[provider] = build_provider(
                    name=provider, kind=kind, base_url=base_url, api_key=api_key
                )
            self.registry.bind_provider(provider, self.providers[provider])

        try:
            cost = CostType(cost_type)
        except ValueError:
            cost = CostType.PAID
        affinity = []
        for t in task_affinity or []:
            try:
                affinity.append(TaskType(t))
            except ValueError:
                continue

        spec = ModelSpec(
            provider=provider, model_name=model_name,
            display_name=display_name or f"{provider}/{model_name}",
            max_context=max_context, cost_type=cost, privacy_level=privacy_level,
            speed_level=speed_level, reasoning_level=reasoning_level,
            coding_level=coding_level, vision_support=vision_support,
            tool_calling_support=tool_calling_support, enabled=True, task_affinity=affinity,
        )
        self.registry.upsert(spec)
        self._provider_config[provider] = {
            "kind": kind, "base_url": base_url, "has_key": bool(api_key)
        }
        # Track + encrypt the API key at rest (the provider also holds it in
        # memory to make calls). Never logged; masked in the credentials UI.
        if api_key:
            from app.security.credentials import CredentialMeta

            ref = f"model:{provider}"
            try:
                self.vault.set(ref, api_key)
            except Exception:  # noqa: BLE001 - NullVault / no key configured
                pass
            self.credentials.register(CredentialMeta(
                name=ref, platform=provider, kind="token", username=None,
                vault_ref=ref, scopes=[kind], requires_approval=True))
        return spec

    def remove_model(self, key: str) -> bool:
        if not self.registry.get(key):
            return False
        self.registry._specs.pop(key, None)
        return True

    def provider_configs(self) -> dict:
        return self._provider_config

    def service_bundle(self) -> dict:
        return {
            "memory": self.memory,
            "tasks": self.tasks,
            "approvals": self.approvals,
            "audit": self.audit,
            "browser": self.browser,
            "learner": self.learner,
            "layered_memory": getattr(self, "layered_memory", None),
        }
