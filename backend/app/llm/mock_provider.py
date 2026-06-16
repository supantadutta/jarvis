"""Deterministic mock provider for tests and offline development.

Returns inspectable, predictable output so the entire orchestration graph
(router, agents, verifier, debate, cascade) can be exercised with zero network
calls and zero API keys.
"""
from __future__ import annotations

import hashlib
import json

from app.llm.base import (
    CompletionRequest,
    CompletionResponse,
    LLMProvider,
    Role,
)


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, *, healthy: bool = True, canned: dict[str, str] | None = None) -> None:
        self._healthy = healthy
        self._canned = canned or {}
        self.calls: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls.append(request)
        user_text = next(
            (m.content for m in reversed(request.messages) if m.role == Role.USER),
            "",
        )

        # Exact canned override (by last user message) wins.
        if user_text in self._canned:
            return self._mk(request, self._canned[user_text])

        if request.json_mode:
            text = self._json_reply(request, user_text)
        else:
            digest = hashlib.sha256(user_text.encode()).hexdigest()[:8]
            text = f"[mock:{request.model}] Response to: {user_text[:120]} (id={digest})"

        return self._mk(request, text)

    def _json_reply(self, request: CompletionRequest, user_text: str) -> str:
        """Heuristic structured replies so JSON-mode agents get parseable output."""
        low = user_text.lower()
        if "classify" in low or "task_type" in low:
            payload = {"task_type": "daily_assistant", "mode": "SINGLE_BEST_MODEL"}
        elif "plan" in low or "steps" in low:
            payload = {
                "steps": [
                    {"description": "Understand the request", "permission": "SAFE_READ", "risk": "none"},
                    {"description": "Produce the answer", "permission": "SAFE_READ", "risk": "low"},
                ]
            }
        elif "verify" in low or "critique" in low:
            # Deterministic for tests: a candidate containing "weak"/"wrong"
            # fails verification, which drives cascade/cost-saver escalation.
            failed = "weak" in low or "wrong" in low
            payload = {
                "passed": not failed,
                "score": 0.3 if failed else 0.9,
                "issues": ["answer is weak/incomplete"] if failed else [],
                "summary": "Needs a stronger model." if failed else "Correct, safe, complete.",
            }
        else:
            payload = {"result": f"mock structured result for {request.model}"}
        return json.dumps(payload)

    @staticmethod
    def _mk(request: CompletionRequest, text: str) -> CompletionResponse:
        return CompletionResponse(
            text=text,
            model=request.model,
            provider="mock",
            prompt_tokens=sum(len(m.content) for m in request.messages) // 4,
            completion_tokens=len(text) // 4,
        )

    async def health(self) -> bool:
        return self._healthy
