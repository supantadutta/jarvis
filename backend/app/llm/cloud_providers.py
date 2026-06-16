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
    Role,
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

    async def stream(self, request: CompletionRequest):  # pragma: no cover - network
        import json

        payload = {
            "model": request.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        async with self._client() as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    delta = (obj.get("choices") or [{}])[0].get("delta", {})
                    chunk = delta.get("content", "")
                    if chunk:
                        yield chunk

    async def health(self) -> bool:  # pragma: no cover - network
        return bool(self.api_key) or "localhost" in self.base_url


# --- pure wire-format builders/parsers (unit-tested without network) ---
def build_anthropic_payload(request: CompletionRequest) -> dict:
    """Map a CompletionRequest to the Anthropic Messages API body.

    Anthropic takes a top-level `system` string and a `messages` list of
    user/assistant turns (no system role inside messages)."""
    system_parts = [m.content for m in request.messages if m.role == Role.SYSTEM]
    turns = [
        {"role": m.role.value, "content": m.content}
        for m in request.messages
        if m.role in (Role.USER, Role.ASSISTANT)
    ]
    payload: dict = {
        "model": request.model,
        "messages": turns,
        "max_tokens": request.max_tokens or 1024,
        "temperature": request.temperature,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if request.tools:
        payload["tools"] = request.tools
    return payload


def parse_anthropic_response(data: dict) -> tuple[str, dict]:
    """Extract text + usage from an Anthropic Messages API response."""
    blocks = data.get("content", []) or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    usage = data.get("usage", {}) or {}
    return text, {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "finish_reason": data.get("stop_reason", "stop"),
    }


def build_gemini_payload(request: CompletionRequest) -> dict:
    """Map a CompletionRequest to the Gemini generateContent body.

    Gemini uses `contents` with roles user/model and an optional
    `systemInstruction`."""
    role_map = {Role.USER: "user", Role.ASSISTANT: "model"}
    contents = [
        {"role": role_map[m.role], "parts": [{"text": m.content}]}
        for m in request.messages
        if m.role in role_map
    ]
    payload: dict = {
        "contents": contents,
        "generationConfig": {"temperature": request.temperature},
    }
    if request.max_tokens:
        payload["generationConfig"]["maxOutputTokens"] = request.max_tokens
    if request.json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    system_parts = [m.content for m in request.messages if m.role == Role.SYSTEM]
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


def parse_gemini_response(data: dict) -> tuple[str, dict]:
    candidates = data.get("candidates", []) or []
    text = ""
    if candidates:
        parts = (candidates[0].get("content", {}) or {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata", {}) or {}
    return text, {
        "prompt_tokens": usage.get("promptTokenCount", 0),
        "completion_tokens": usage.get("candidatesTokenCount", 0),
        "finish_reason": (candidates[0].get("finishReason", "stop") if candidates else "stop"),
    }


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API (anthropic-version 2023-06-01)."""

    name = "anthropic"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str | None, base_url: str = "https://api.anthropic.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        if not self.api_key:
            raise ProviderError("anthropic: no API key configured.")
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise ProviderError("httpx is required for the Anthropic provider.") from exc
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/messages", json=build_anthropic_payload(request)
                )
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"anthropic request failed: {exc}") from exc
            data = resp.json()
        text, meta = parse_anthropic_response(data)
        return CompletionResponse(
            text=text, model=request.model, provider=self.name,
            prompt_tokens=meta["prompt_tokens"], completion_tokens=meta["completion_tokens"],
            finish_reason=meta["finish_reason"], raw=data,
        )

    async def health(self) -> bool:  # pragma: no cover
        return bool(self.api_key)


class GeminiProvider(LLMProvider):
    """Google Gemini Generative Language API (generateContent)."""

    name = "google"

    def __init__(self, api_key: str | None,
                 base_url: str = "https://generativelanguage.googleapis.com/v1beta") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        if not self.api_key:
            raise ProviderError("google: no API key configured.")
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise ProviderError("httpx is required for the Gemini provider.") from exc
        url = f"{self.base_url}/models/{request.model}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(url, json=build_gemini_payload(request))
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"gemini request failed: {exc}") from exc
            data = resp.json()
        text, meta = parse_gemini_response(data)
        return CompletionResponse(
            text=text, model=request.model, provider=self.name,
            prompt_tokens=meta["prompt_tokens"], completion_tokens=meta["completion_tokens"],
            finish_reason=meta["finish_reason"], raw=data,
        )

    async def health(self) -> bool:  # pragma: no cover
        return bool(self.api_key)
