"""Task + task-step tracking (in-memory for Phase 1)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    index: int
    description: str
    permission: str
    risk: str
    agent: str | None = None
    tool: str | None = None
    status: str = "pending"
    output_summary: str = ""
    approval_id: str | None = None


@dataclass
class Task:
    id: str
    command: str
    task_type: str
    mode: str
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStep] = field(default_factory=list)
    result: str = ""
    models: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    error: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()

    def public(self) -> dict:
        return {
            "id": self.id,
            "command": self.command,
            "task_type": self.task_type,
            "mode": self.mode,
            "status": self.status.value,
            "result": self.result,
            "models": self.models,
            "agents": self.agents,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "steps": [
                {
                    "index": s.index,
                    "description": s.description,
                    "permission": s.permission,
                    "risk": s.risk,
                    "agent": s.agent,
                    "tool": s.tool,
                    "status": s.status,
                    "output_summary": s.output_summary,
                    "approval_id": s.approval_id,
                }
                for s in self.steps
            ],
        }


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def create(self, command: str, task_type: str, mode: str) -> Task:
        task = Task(id=uuid.uuid4().hex[:12], command=command, task_type=task_type, mode=mode)
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all(self, limit: int = 50) -> list[Task]:
        items = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return items[:limit]
