"""Cloud provider scaffolds (Phase 2 wiring).

`OpenAICompatibleProvider` already covers OpenAI, Groq, OpenRouter, and any
OpenAI-compatible local API (e.g. LM Studio, vLLM) via different base URLs.
Anthropic and Gemini use distinct wire formats and are stubbed with a clear
interface to fill in during Phase 2.

All network deps are imported lazily; importing this module never requires keys
or httpx, so the test suite stays hermetic.
"""
from __future__ import annotations

from app.llm.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    ProviderError,
)


class OpenAICompatibleProvider(LLMProvider):
    """Works with any OpenAI `/chat/completions`-compatible endpoint."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str | None,
        timeout: float = 120.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _client(self):  # pragma: no cover - thin httpx wrapper
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise ProviderError("httpx is required for cloud providers.") from exc
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.AsyncClient(timeout=self.timeout, headers=headers)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise ProviderError(f"{self.name}: no API key configured.")
        payload = {
            "model": request.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = request.tools

        async with self._client() as client:
            try:
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"{self.name} request failed: {exc}") from exc
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "")
        usage = data.get("usage", {})
        return CompletionResponse(
            text=text,
            model=request.model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def health(self) -> bool:  # pragma: no cover - network
        return bool(self.api_key) or "localhost" in self.base_url


class AnthropicProvider(LLMProvider):
    """Stub — implement the Messages API in Phase 2."""

    name = "anthropic"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        raise ProviderError("AnthropicProvider is scaffolded; implement in Phase 2.")

    async def health(self) -> bool:  # pragma: no cover
        return bool(self.api_key)


class GeminiProvider(LLMProvider):
    """Stub — implement the Generative Language API in Phase 2."""

    name = "google"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        raise ProviderError("GeminiProvider is scaffolded; implement in Phase 2.")

    async def health(self) -> bool:  # pragma: no cover
        return bool(self.api_key)
