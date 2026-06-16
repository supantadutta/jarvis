"""Ollama provider — the local-first default.

Talks to a local Ollama server (`/api/chat`). `httpx` is imported lazily so the
package can be imported (and the rest of the app tested) without httpx or a
running Ollama instance.
"""
from __future__ import annotations

from app.llm.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    ProviderError,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self):  # pragma: no cover - thin wrapper around httpx
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise ProviderError(
                "httpx is required for the Ollama provider. Install backend deps."
            ) from exc
        return httpx.AsyncClient(timeout=self.timeout)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        payload = {
            "model": request.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.json_mode:
            payload["format"] = "json"
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        async with self._client() as client:
            try:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"Ollama request failed: {exc}") from exc
            data = resp.json()

        text = (data.get("message") or {}).get("content", "")
        return CompletionResponse(
            text=text,
            model=request.model,
            provider=self.name,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            finish_reason=data.get("done_reason", "stop"),
            raw=data,
        )

    async def health(self) -> bool:  # pragma: no cover - network
        try:
            async with self._client() as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False
