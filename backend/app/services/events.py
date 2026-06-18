"""In-process event bus for the dashboard's live agent-activity timeline.

The audit log feeds events in (via a listener); WebSocket clients subscribe and
receive a snapshot of recent events plus new ones as they happen. Kept simple and
loop-agnostic: a bounded ring buffer of recent events + per-subscriber queues
that are fed best-effort (a slow/full subscriber never blocks auditing).
"""
from __future__ import annotations

import asyncio
from collections import deque


class EventBus:
    def __init__(self, history: int = 200) -> None:
        self._recent: deque[dict] = deque(maxlen=history)
        self._subscribers: list[asyncio.Queue] = []

    def publish(self, event: dict) -> None:
        self._recent.append(event)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # drop for a slow consumer; never block the producer

    def snapshot(self, limit: int = 50) -> list[dict]:
        return list(self._recent)[-limit:]

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def audit_listener(self):
        """Return a callback to attach to AuditLog.add_listener()."""
        def _cb(entry):
            self.publish({
                "type": "audit",
                "id": entry.id, "timestamp": entry.timestamp, "agent": entry.agent,
                "model": entry.model, "tool": entry.tool, "risk": entry.risk,
                "approval_status": entry.approval_status,
                "summary": entry.output_summary or entry.error or "",
            })
        return _cb
