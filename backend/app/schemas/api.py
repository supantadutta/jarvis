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


class EmergencyStop(BaseModel):
    engaged: bool
