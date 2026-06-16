"""Model registry: capability tags + seed models + provider binding.

Each model carries the capability metadata the Model Router scores on. The
registry also binds models to a concrete provider instance and exposes health
checks. Local Ollama models are seeded enabled by default; cloud models are
seeded but only become *available* when their provider has an API key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.llm.base import LLMProvider


class CostType(str, Enum):
    LOCAL = "local"
    FREE = "free"
    PAID = "paid"


class TaskType(str, Enum):
    DAILY_ASSISTANT = "daily_assistant"
    RESEARCH = "research"
    CODING = "coding"
    DOCUMENT_GENERATION = "document_generation"
    BROWSER_AUTOMATION = "browser_automation"
    DESKTOP_AUTOMATION = "desktop_automation"
    CYBERSECURITY = "cybersecurity"
    REPORT_WRITING = "report_writing"
    DATA_ANALYSIS = "data_analysis"
    PLANNING = "planning"
    VERIFICATION = "verification"
    VOICE_COMMAND = "voice_command"
    WORKFLOW_EXECUTION = "workflow_execution"


# Capability levels are integers 0..5.
@dataclass
class ModelSpec:
    provider: str
    model_name: str
    display_name: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    max_context: int = 8192
    cost_type: CostType = CostType.LOCAL
    privacy_level: int = 5  # 5 = fully local/private, 1 = third-party cloud
    speed_level: int = 3
    reasoning_level: int = 3
    coding_level: int = 3
    vision_support: bool = False
    tool_calling_support: bool = False
    enabled: bool = True
    fallback_priority: int = 50  # lower = tried earlier in cascades
    # Task affinities give a router bonus for matching task types.
    task_affinity: list[TaskType] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model_name}"

    @property
    def is_local(self) -> bool:
        return self.cost_type in (CostType.LOCAL, CostType.FREE) and self.provider in (
            "ollama",
            "openai_compatible",
        )


def seed_models() -> list[ModelSpec]:
    """Default registry. Cloud entries are present but disabled until keyed."""
    T = TaskType
    return [
        # --- Local Ollama models (default, private) ---
        ModelSpec(
            provider="ollama",
            model_name="qwen2.5-coder",
            display_name="Qwen2.5 Coder (local)",
            strengths=["coding", "tool-calls", "fast"],
            weaknesses=["long-context reasoning"],
            max_context=32768,
            cost_type=CostType.LOCAL,
            privacy_level=5,
            speed_level=4,
            reasoning_level=3,
            coding_level=5,
            tool_calling_support=True,
            fallback_priority=10,
            task_affinity=[T.CODING, T.DESKTOP_AUTOMATION, T.WORKFLOW_EXECUTION],
        ),
        ModelSpec(
            provider="ollama",
            model_name="llama3.1",
            display_name="Llama 3.1 8B (local)",
            strengths=["general", "reasoning", "tool-calls"],
            weaknesses=["heavy coding"],
            max_context=131072,
            cost_type=CostType.LOCAL,
            privacy_level=5,
            speed_level=3,
            reasoning_level=4,
            coding_level=3,
            tool_calling_support=True,
            fallback_priority=20,
            task_affinity=[T.DAILY_ASSISTANT, T.PLANNING, T.RESEARCH, T.REPORT_WRITING],
        ),
        ModelSpec(
            provider="ollama",
            model_name="mistral",
            display_name="Mistral 7B (local)",
            strengths=["fast", "general"],
            weaknesses=["complex reasoning"],
            max_context=32768,
            cost_type=CostType.LOCAL,
            privacy_level=5,
            speed_level=5,
            reasoning_level=3,
            coding_level=3,
            fallback_priority=15,
            task_affinity=[T.DAILY_ASSISTANT, T.VOICE_COMMAND, T.VERIFICATION],
        ),
        ModelSpec(
            provider="ollama",
            model_name="deepseek-coder-v2",
            display_name="DeepSeek Coder V2 (local)",
            strengths=["coding", "debugging"],
            weaknesses=["chit-chat"],
            max_context=16384,
            cost_type=CostType.LOCAL,
            privacy_level=5,
            speed_level=3,
            reasoning_level=4,
            coding_level=5,
            fallback_priority=12,
            task_affinity=[T.CODING, T.CYBERSECURITY, T.DATA_ANALYSIS],
        ),
        # --- Cloud models (optional; disabled until API key present) ---
        ModelSpec(
            provider="openai",
            model_name="gpt-4o",
            display_name="OpenAI GPT-4o",
            strengths=["reasoning", "vision", "tool-calls"],
            weaknesses=["paid", "non-private"],
            max_context=128000,
            cost_type=CostType.PAID,
            privacy_level=1,
            speed_level=4,
            reasoning_level=5,
            coding_level=5,
            vision_support=True,
            tool_calling_support=True,
            enabled=False,
            fallback_priority=60,
            task_affinity=[T.RESEARCH, T.REPORT_WRITING, T.PLANNING, T.CODING],
        ),
        ModelSpec(
            provider="anthropic",
            model_name="claude-sonnet-4",
            display_name="Anthropic Claude Sonnet 4",
            strengths=["reasoning", "writing", "coding", "long-context"],
            weaknesses=["paid", "non-private"],
            max_context=200000,
            cost_type=CostType.PAID,
            privacy_level=1,
            speed_level=4,
            reasoning_level=5,
            coding_level=5,
            tool_calling_support=True,
            enabled=False,
            fallback_priority=62,
            task_affinity=[T.REPORT_WRITING, T.CODING, T.RESEARCH, T.VERIFICATION],
        ),
        ModelSpec(
            provider="google",
            model_name="gemini-2.0-flash",
            display_name="Google Gemini 2.0 Flash",
            strengths=["fast", "vision", "long-context"],
            weaknesses=["non-private"],
            max_context=1000000,
            cost_type=CostType.PAID,
            privacy_level=1,
            speed_level=5,
            reasoning_level=4,
            coding_level=4,
            vision_support=True,
            tool_calling_support=True,
            enabled=False,
            fallback_priority=64,
            task_affinity=[T.RESEARCH, T.DATA_ANALYSIS, T.DAILY_ASSISTANT],
        ),
        ModelSpec(
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            display_name="Groq Llama 3.3 70B",
            strengths=["very fast", "reasoning"],
            weaknesses=["non-private"],
            max_context=128000,
            cost_type=CostType.FREE,
            privacy_level=2,
            speed_level=5,
            reasoning_level=4,
            coding_level=4,
            tool_calling_support=True,
            enabled=False,
            fallback_priority=55,
            task_affinity=[T.DAILY_ASSISTANT, T.RESEARCH, T.PLANNING],
        ),
        ModelSpec(
            provider="openrouter",
            model_name="auto",
            display_name="OpenRouter (auto-route)",
            strengths=["flexible", "many models"],
            weaknesses=["non-private", "variable"],
            max_context=128000,
            cost_type=CostType.PAID,
            privacy_level=1,
            speed_level=3,
            reasoning_level=4,
            coding_level=4,
            tool_calling_support=True,
            enabled=False,
            fallback_priority=70,
            task_affinity=[T.RESEARCH, T.REPORT_WRITING],
        ),
    ]


class ModelRegistry:
    """Holds model specs and their bound providers; exposes health checks."""

    def __init__(self) -> None:
        self._specs: dict[str, ModelSpec] = {}
        self._providers: dict[str, LLMProvider] = {}
        for spec in seed_models():
            self._specs[spec.key] = spec

    # --- specs ---
    def all(self) -> list[ModelSpec]:
        return list(self._specs.values())

    def enabled(self) -> list[ModelSpec]:
        return [s for s in self._specs.values() if s.enabled]

    def get(self, key: str) -> ModelSpec | None:
        return self._specs.get(key)

    def upsert(self, spec: ModelSpec) -> None:
        self._specs[spec.key] = spec

    def set_enabled(self, key: str, enabled: bool) -> bool:
        spec = self._specs.get(key)
        if not spec:
            return False
        spec.enabled = enabled
        return True

    # --- providers ---
    def bind_provider(self, provider_name: str, provider: LLMProvider) -> None:
        self._providers[provider_name] = provider
        # Enable models whose provider just became available (if keyed).
        for spec in self._specs.values():
            if spec.provider == provider_name and provider_name != "mock":
                spec.enabled = spec.enabled or provider_name in ("ollama", "openai_compatible")

    def provider_for(self, spec: ModelSpec) -> LLMProvider | None:
        return self._providers.get(spec.provider)

    async def health(self, key: str) -> bool:
        spec = self.get(key)
        if not spec:
            return False
        provider = self.provider_for(spec)
        if not provider:
            return False
        try:
            return await provider.health()
        except Exception:  # noqa: BLE001
            return False

    async def health_cached(self, key: str, *, ttl: float = 30.0) -> bool:
        """Health check with a short TTL cache to avoid hammering providers."""
        import time

        if not hasattr(self, "_health_cache"):
            self._health_cache: dict[str, tuple[float, bool]] = {}
        now = time.monotonic()
        cached = self._health_cache.get(key)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
        ok = await self.health(key)
        self._health_cache[key] = (now, ok)
        return ok

    async def available(self, *, ttl: float = 30.0) -> list[ModelSpec]:
        """Enabled models whose provider currently passes its health check."""
        out: list[ModelSpec] = []
        for spec in self.enabled():
            if await self.health_cached(spec.key, ttl=ttl):
                out.append(spec)
        return out
