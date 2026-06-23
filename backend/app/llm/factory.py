"""Provider factory — build an LLM provider from runtime config.

Lets the dashboard connect ANY model: pick a kind (ollama / openai-compatible /
openai / anthropic / google / groq / openrouter / custom), give a base URL +
API key, and it becomes usable immediately — no code edits. Most "OpenAI-style"
endpoints (LM Studio, vLLM, Together, Fireworks, DeepSeek, Mistral, local
gateways, …) work through the openai_compatible kind.
"""
from __future__ import annotations

from app.llm.base import LLMProvider

# Known base URLs for convenience; any custom base_url also works.
KNOWN_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
}


def build_provider(
    *, name: str, kind: str, base_url: str | None = None, api_key: str | None = None
) -> LLMProvider:
    """Construct a provider for a runtime-registered model source."""
    kind = (kind or "openai_compatible").lower()

    if kind == "ollama":
        from app.llm.ollama_provider import OllamaProvider

        return OllamaProvider(base_url or "http://localhost:11434")

    if kind == "anthropic":
        from app.llm.cloud_providers import AnthropicProvider

        return AnthropicProvider(api_key, base_url or "https://api.anthropic.com/v1")

    if kind in ("google", "gemini"):
        from app.llm.cloud_providers import GeminiProvider

        return GeminiProvider(
            api_key, base_url or "https://generativelanguage.googleapis.com/v1beta"
        )

    # Everything else is treated as OpenAI-compatible (the common case).
    from app.llm.cloud_providers import OpenAICompatibleProvider

    resolved = base_url or KNOWN_BASE_URLS.get(kind) or KNOWN_BASE_URLS["openai"]
    return OpenAICompatibleProvider(name=name, base_url=resolved, api_key=api_key)
