"""SQLModel table definitions for the full JARVIS schema.

Phase 1 runs on in-memory runtime services for speed and hermetic tests; these
tables define the persistent schema and are created at startup so Phase 2 can
move the runtime stores onto the database without schema churn.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import JSON, Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: int | None = Field(default=None, primary_key=True)
    name: str = "owner"
    email: str | None = None
    is_admin: bool = True
    created_at: datetime = Field(default_factory=_now)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=_now)


class ModelProvider(SQLModel, table=True):
    __tablename__ = "model_providers"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    kind: str = "local"  # local | cloud
    base_url: str | None = None
    enabled: bool = True


class ModelRow(SQLModel, table=True):
    __tablename__ = "models"
    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    model_name: str
    display_name: str
    cost_type: str = "local"
    privacy_level: int = 5
    speed_level: int = 3
    reasoning_level: int = 3
    coding_level: int = 3
    max_context: int = 8192
    vision_support: bool = False
    tool_calling_support: bool = False
    enabled: bool = True
    fallback_priority: int = 50
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Agent(SQLModel, table=True):
    __tablename__ = "agents"
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True)
    display_name: str
    default_task_type: str = "daily_assistant"
    enabled: bool = True


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    id: int | None = Field(default=None, primary_key=True)
    task_id: str | None = Field(default=None, index=True)
    agent: str
    model: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=_now)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"
    id: int | None = Field(default=None, primary_key=True)
    role: str = "user"
    content: str = ""
    task_id: str | None = Field(default=None, index=True)
    source: str = "dashboard"  # dashboard | telegram | voice
    created_at: datetime = Field(default_factory=_now)


class TaskRow(SQLModel, table=True):
    __tablename__ = "tasks"
    id: str = Field(primary_key=True)
    command: str
    task_type: str
    mode: str
    status: str = "pending"
    result: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class TaskStepRow(SQLModel, table=True):
    __tablename__ = "task_steps"
    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    idx: int = 0
    description: str = ""
    permission: str = "SAFE_READ"
    risk: str = "low"
    status: str = "pending"
    approval_id: str | None = None


class ApprovalRow(SQLModel, table=True):
    __tablename__ = "approvals"
    id: str = Field(primary_key=True)
    task_id: str | None = Field(default=None, index=True)
    tool: str = ""
    agent: str = ""
    risk: str = "low"
    status: str = "pending"
    action_preview: str = ""
    created_at: datetime = Field(default_factory=_now)
    resolved_at: datetime | None = None


class ToolRow(SQLModel, table=True):
    __tablename__ = "tools"
    name: str = Field(primary_key=True)
    description: str = ""
    permission: str = "SAFE_READ"
    risk: str = "low"
    requires_approval: bool = False


class ToolCall(SQLModel, table=True):
    __tablename__ = "tool_calls"
    id: int | None = Field(default=None, primary_key=True)
    task_id: str | None = Field(default=None, index=True)
    tool: str = ""
    agent: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    decision: str = ""
    approval_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class AuditLogRow(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: str = Field(primary_key=True)
    timestamp: datetime = Field(default_factory=_now)
    user_command: str | None = None
    agent: str | None = None
    model: str | None = None
    tool: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    risk: str = "low"
    approval_status: str = "n/a"
    screenshot_ref: str | None = None
    error: str | None = None


class CredentialMetadata(SQLModel, table=True):
    __tablename__ = "credentials_metadata"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    platform: str = ""
    kind: str = "password"  # password | token | oauth | session
    username: str | None = None
    vault_ref: str = ""  # pointer into the vault; NEVER the secret itself
    scopes: str = ""
    requires_approval: bool = True
    revoked: bool = False
    created_at: datetime = Field(default_factory=_now)
    last_used_at: datetime | None = None


class BrowserProfile(SQLModel, table=True):
    __tablename__ = "browser_profiles"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    storage_state_ref: str | None = None  # encrypted storage_state pointer
    allowed_domains: str = ""
    headless: bool = False


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    id: int | None = Field(default=None, primary_key=True)
    path: str
    title: str = ""
    mime: str = ""
    indexed: bool = False
    created_at: datetime = Field(default_factory=_now)


class MemoryChunk(SQLModel, table=True):
    __tablename__ = "memory_chunks"
    id: str = Field(primary_key=True)
    collection: str = "default"
    text: str = ""
    source: str | None = None
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)


class Workflow(SQLModel, table=True):
    __tablename__ = "workflows"
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True)
    name: str = ""
    trigger: str = "manual"
    schedule: str | None = None
    risk_level: str = "low"
    approval_policy: str = "auto_safe"
    definition: dict = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True


class WorkflowRun(SQLModel, table=True):
    __tablename__ = "workflow_runs"
    id: int | None = Field(default=None, primary_key=True)
    workflow_key: str = Field(index=True)
    status: str = "pending"
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    output_location: str | None = None


class TelegramUser(SQLModel, table=True):
    __tablename__ = "telegram_users"
    telegram_id: int = Field(primary_key=True)
    username: str | None = None
    allowed: bool = False
    created_at: datetime = Field(default_factory=_now)


class VoiceSession(SQLModel, table=True):
    __tablename__ = "voice_sessions"
    id: int | None = Field(default=None, primary_key=True)
    transcript: str = ""
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=_now)


class Screenshot(SQLModel, table=True):
    __tablename__ = "screenshots"
    id: int | None = Field(default=None, primary_key=True)
    path: str
    source: str = "desktop"  # desktop | browser
    task_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_now)


class FileIndex(SQLModel, table=True):
    __tablename__ = "files_index"
    id: int | None = Field(default=None, primary_key=True)
    path: str = Field(index=True)
    size: int = 0
    mtime: float = 0.0
    hash: str | None = None


class ModelEvaluation(SQLModel, table=True):
    __tablename__ = "model_evaluations"
    id: int | None = Field(default=None, primary_key=True)
    model_key: str = Field(index=True)
    task_type: str = ""
    success_rate: float = 0.0
    samples: int = 0
    updated_at: datetime = Field(default_factory=_now)


class AIComparison(SQLModel, table=True):
    __tablename__ = "ai_comparisons"
    id: int | None = Field(default=None, primary_key=True)
    task_id: str | None = Field(default=None, index=True)
    candidates: dict = Field(default_factory=dict, sa_column=Column(JSON))
    winner_index: int = 0
    judged_by: str | None = None
    created_at: datetime = Field(default_factory=_now)
