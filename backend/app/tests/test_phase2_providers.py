"""Phase 2: cloud provider wire-format builders (no network)."""
from __future__ import annotations

from app.llm.base import ChatMessage, CompletionRequest, Role
from app.llm.cloud_providers import (
    build_anthropic_payload,
    build_gemini_payload,
    parse_anthropic_response,
    parse_gemini_response,
)


def _req(json_mode=False):
    return CompletionRequest(
        model="m",
        messages=[
            ChatMessage(Role.SYSTEM, "be helpful"),
            ChatMessage(Role.USER, "hello"),
            ChatMessage(Role.ASSISTANT, "hi"),
            ChatMessage(Role.USER, "more"),
        ],
        temperature=0.3,
        max_tokens=256,
        json_mode=json_mode,
    )


def test_anthropic_payload_splits_system_and_turns():
    p = build_anthropic_payload(_req())
    assert p["system"] == "be helpful"
    assert p["max_tokens"] == 256
    # system must NOT be inside messages
    assert all(m["role"] in ("user", "assistant") for m in p["messages"])
    assert len(p["messages"]) == 3


def test_anthropic_parse_extracts_text_and_usage():
    data = {
        "content": [{"type": "text", "text": "answer"}, {"type": "tool_use"}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn",
    }
    text, meta = parse_anthropic_response(data)
    assert text == "answer"
    assert meta["prompt_tokens"] == 10 and meta["completion_tokens"] == 5
    assert meta["finish_reason"] == "end_turn"


def test_gemini_payload_roles_and_system_instruction():
    p = build_gemini_payload(_req(json_mode=True))
    assert p["systemInstruction"]["parts"][0]["text"] == "be helpful"
    roles = [c["role"] for c in p["contents"]]
    assert roles == ["user", "model", "user"]  # assistant -> model
    assert p["generationConfig"]["responseMimeType"] == "application/json"
    assert p["generationConfig"]["maxOutputTokens"] == 256


def test_gemini_parse_extracts_text():
    data = {
        "candidates": [
            {"content": {"parts": [{"text": "hi "}, {"text": "there"}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2},
    }
    text, meta = parse_gemini_response(data)
    assert text == "hi there"
    assert meta["prompt_tokens"] == 7
    assert meta["finish_reason"] == "STOP"
