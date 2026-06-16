"""Approval queue.

When the Permission Guard returns REQUIRES_APPROVAL, an Approval is created and
the task step waits (an asyncio.Event) until a human approves or denies it via
the dashboard, Telegram, or the API. In-memory store for Phase 1; the
`approvals` table mirrors the schema for Phase 2 persistence.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    TRUSTED = "trusted"  # approved + "trust this workflow"


@dataclass
class ApprovalRequest:
    """Everything the human sees before deciding (see security_model.md)."""

    task_name: str
    requested_action: str
    agent: str
    model: str | None
    tool: str
    account: str | None
    credential: str | None
    risk: str
    what_can_change: str
    action_preview: str
    allow_trust: bool = False  # offer "trust this workflow"?


@dataclass
class Approval:
    id: str
    request: ApprovalRequest
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    note: str | None = None
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def public(self) -> dict:
        r = self.request
        return {
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "task_name": r.task_name,
            "requested_action": r.requested_action,
            "agent": r.agent,
            "model": r.model,
            "tool": r.tool,
            "account": r.account,
            "credential": r.credential,
            "risk": r.risk,
            "what_can_change": r.what_can_change,
            "action_preview": r.action_preview,
            "allow_trust": r.allow_trust,
        }


class ApprovalQueue:
    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}
        self._listeners: list = []

    def add_listener(self, cb) -> None:
        """Register a callback invoked on create/resolve (write-through)."""
        self._listeners.append(cb)

    def _notify(self, approval: Approval) -> None:
        for cb in self._listeners:
            try:
                cb(approval)
            except Exception:  # noqa: BLE001 - persistence must not break approvals
                pass

    def create(self, request: ApprovalRequest) -> Approval:
        approval = Approval(id=uuid.uuid4().hex[:12], request=request)
        self._items[approval.id] = approval
        self._notify(approval)
        return approval

    def get(self, approval_id: str) -> Approval | None:
        return self._items.get(approval_id)

    def pending(self) -> list[Approval]:
        return [a for a in self._items.values() if a.status == ApprovalStatus.PENDING]

    def all(self) -> list[Approval]:
        return list(self._items.values())

    def resolve(
        self,
        approval_id: str,
        approved: bool,
        *,
        resolved_by: str = "user",
        trust: bool = False,
        note: str | None = None,
    ) -> Approval | None:
        approval = self._items.get(approval_id)
        if not approval or approval.status != ApprovalStatus.PENDING:
            return approval
        if approved:
            approval.status = ApprovalStatus.TRUSTED if trust else ApprovalStatus.APPROVED
        else:
            approval.status = ApprovalStatus.DENIED
        approval.resolved_at = datetime.now(UTC)
        approval.resolved_by = resolved_by
        approval.note = note
        approval._event.set()
        self._notify(approval)
        return approval

    async def wait(self, approval_id: str, timeout: float | None = None) -> Approval | None:
        approval = self._items.get(approval_id)
        if not approval:
            return None
        try:
            await asyncio.wait_for(approval._event.wait(), timeout=timeout)
        except TimeoutError:
            if approval.status == ApprovalStatus.PENDING:
                approval.status = ApprovalStatus.EXPIRED
                approval.resolved_at = datetime.now(UTC)
        return approval

    @staticmethod
    def is_granted(approval: Approval | None) -> bool:
        return approval is not None and approval.status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.TRUSTED,
        )
