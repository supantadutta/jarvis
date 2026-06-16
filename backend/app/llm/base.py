"""LLM provider abstraction.

A provider knows how to turn a list of chat messages into a completion for a
given model. Providers are interchangeable; the Model Router decides *which*
model/provider to use, and agents call the provider through a uniform interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ChatMessage:
    role: Role
    content: str
    name: str | None = None


@dataclass
class CompletionRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.2
    max_tokens: int | None = None
    json_mode: bool = False
    # Tool/function schemas (OpenAI-style) for tool-calling models.
    tools: list[dict] | None = None


@dataclass
class CompletionResponse:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete a request."""


class LLMProvider(Protocol):
    """Interface every provider implements."""

    name: str

    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    async def health(self) -> bool:
        """Cheap availability check used by the router/registry."""
        ...


async def stream_text(provider: "LLMProvider", request: CompletionRequest):
    """Yield text chunks from a provider, using native streaming when available
    and falling back to a single complete() call otherwise."""
    streamer = getattr(provider, "stream", None)
    if streamer is not None:
        async for chunk in streamer(request):
            if chunk:
                yield chunk
        return
    resp = await provider.complete(request)
    yield resp.text
