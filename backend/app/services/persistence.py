"""Persistence repository (Phase 2).

Bridges the in-memory runtime objects (Task, Approval, AuditEntry, chat) onto the
SQLModel tables so state survives restarts. Kept as explicit functions (rather
than wired write-through into every hot path) so the core stays fast and the
test suite stays hermetic; the API/orchestrator can opt in to persistence.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.audit.logger import AuditEntry
from app.models.tables import (
    AuditLogRow,
    ChatMessage,
    TaskRow,
    TaskStepRow,
)
from app.services.approvals import Approval
from app.models.tables import ApprovalRow
from app.services.tasks import Task


def persist_task(session: Session, task: Task) -> None:
    row = session.get(TaskRow, task.id)
    if row is None:
        row = TaskRow(id=task.id, command=task.command, task_type=task.task_type, mode=task.mode)
        session.add(row)
    row.status = task.status.value
    row.result = task.result
    row.task_type = task.task_type
    row.mode = task.mode
    # Replace steps for this task.
    existing = session.exec(select(TaskStepRow).where(TaskStepRow.task_id == task.id)).all()
    for s in existing:
        session.delete(s)
    for step in task.steps:
        session.add(
            TaskStepRow(
                task_id=task.id, idx=step.index, description=step.description,
                permission=step.permission, risk=step.risk, status=step.status,
                approval_id=step.approval_id,
            )
        )
    session.commit()


def load_task(session: Session, task_id: str) -> dict | None:
    row = session.get(TaskRow, task_id)
    if row is None:
        return None
    steps = session.exec(select(TaskStepRow).where(TaskStepRow.task_id == task_id)).all()
    return {
        "id": row.id, "command": row.command, "task_type": row.task_type,
        "mode": row.mode, "status": row.status, "result": row.result,
        "steps": [{"index": s.idx, "description": s.description, "permission": s.permission,
                   "risk": s.risk, "status": s.status} for s in sorted(steps, key=lambda s: s.idx)],
    }


def persist_approval(session: Session, approval: Approval) -> None:
    row = session.get(ApprovalRow, approval.id)
    r = approval.request
    if row is None:
        row = ApprovalRow(id=approval.id, tool=r.tool, agent=r.agent, risk=r.risk,
                          action_preview=r.action_preview)
        session.add(row)
    row.status = approval.status.value
    if approval.resolved_at:
        row.resolved_at = approval.resolved_at
    session.commit()


def persist_audit(session: Session, entry: AuditEntry) -> None:
    if session.get(AuditLogRow, entry.id) is not None:
        return
    session.add(
        AuditLogRow(
            id=entry.id, timestamp=datetime.fromisoformat(entry.timestamp),
            user_command=entry.user_command, agent=entry.agent, model=entry.model,
            tool=entry.tool, input_summary=entry.input_summary,
            output_summary=entry.output_summary, risk=entry.risk,
            approval_status=entry.approval_status, screenshot_ref=entry.screenshot_ref,
            error=entry.error,
        )
    )
    session.commit()


def persist_chat(session: Session, *, role: str, content: str, task_id: str | None,
                 source: str = "dashboard") -> None:
    session.add(ChatMessage(role=role, content=content, task_id=task_id, source=source))
    session.commit()


def count_rows(session: Session, model) -> int:
    return len(session.exec(select(model)).all())


# --- memory write-through + hydration (DB as the durable source of truth) ---
def persist_memory(session: Session, item) -> None:
    from app.models.tables import MemoryChunk

    if session.get(MemoryChunk, item.id) is not None:
        return
    session.add(MemoryChunk(
        id=item.id, collection=item.collection, text=item.text,
        source=item.source, meta=item.metadata or {}))
    session.commit()


def load_memory(session: Session) -> list:
    """Return all persisted memory items as in-memory MemoryItem objects."""
    from collections import Counter
    import re

    from app.models.tables import MemoryChunk
    from app.rag.memory import MemoryItem

    _tok = re.compile(r"[a-z0-9]+")
    out = []
    for row in session.exec(select(MemoryChunk)).all():
        out.append(MemoryItem(
            id=row.id, text=row.text, collection=row.collection,
            metadata=row.meta or {}, source=row.source,
            created_at=row.created_at.isoformat() if row.created_at else "",
            _vec=Counter(_tok.findall(row.text.lower())),
        ))
    return out


def load_tasks(session: Session) -> list[dict]:
    rows = session.exec(select(TaskRow)).all()
    out = []
    for row in rows:
        steps = session.exec(select(TaskStepRow).where(TaskStepRow.task_id == row.id)).all()
        out.append({
            "id": row.id, "command": row.command, "task_type": row.task_type,
            "mode": row.mode, "status": row.status, "result": row.result,
            "steps": sorted(({"index": s.idx, "description": s.description,
                              "permission": s.permission, "risk": s.risk,
                              "status": s.status, "approval_id": s.approval_id}
                             for s in steps), key=lambda s: s["index"]),
        })
    return out
