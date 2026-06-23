"""Pydantic request/response schemas for the HTTP API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: str | None = None  # optional explicit Mode name
    source: str = "dashboard"


class ChatResponse(BaseModel):
    task_id: str
    answer: str
    task_type: str
    mode: str
    models: list[str]
    agents: list[str]
    plan: list[dict] = []
    verifier: dict | None = None
    candidates: list[dict] = []
    pending_approvals: list[str] = []
    attempts: list[str] = []
    analysis: dict | None = None
    quality: dict | None = None


class ApprovalDecision(BaseModel):
    approved: bool
    trust: bool = False
    note: str | None = None


class MemoryAddRequest(BaseModel):
    text: str = Field(min_length=1)
    collection: str = "default"
    source: str | None = None


class MemorySearchRequest(BaseModel):
    query: str
    collection: str | None = None
    limit: int = 5


class ModelToggle(BaseModel):
    enabled: bool


class AddModelRequest(BaseModel):
    provider: str = Field(min_length=1)  # logical provider name, e.g. "deepseek"
    model_name: str = Field(min_length=1)  # e.g. "deepseek-chat"
    display_name: str | None = None
    kind: str = "openai_compatible"  # ollama|openai_compatible|anthropic|google|...
    base_url: str | None = None
    api_key: str | None = None  # stored as "has_key" only; secret kept in memory
    cost_type: str = "paid"
    privacy_level: int = 1
    reasoning_level: int = 4
    coding_level: int = 4
    speed_level: int = 3
    max_context: int = 32768
    vision_support: bool = False
    tool_calling_support: bool = True
    task_affinity: list[str] = []


class EmergencyStop(BaseModel):
    engaged: bool
