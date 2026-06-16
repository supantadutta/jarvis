"""Append-only audit log with secret redaction.

Every agent run, model call, and tool call is recorded with input/output
summaries (redacted), risk level, approval status, and an optional screenshot
reference. In-memory ring + JSONL file sink; mirrors the `audit_logs` schema.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.security.prompt_injection import redact_secrets


@dataclass
class AuditEntry:
    id: str
    timestamp: str
    user_command: str | None
    agent: str | None
    model: str | None
    tool: str | None
    input_summary: str
    output_summary: str
    risk: str
    approval_status: str
    screenshot_ref: str | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


class AuditLog:
    def __init__(self, sink_path: str | None = None, max_memory: int = 2000) -> None:
        self._entries: list[AuditEntry] = []
        self._max = max_memory
        self._lock = threading.Lock()
        self.sink_path = Path(sink_path) if sink_path else None
        if self.sink_path:
            self.sink_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        user_command: str | None = None,
        agent: str | None = None,
        model: str | None = None,
        tool: str | None = None,
        input_summary: str = "",
        output_summary: str = "",
        risk: str = "low",
        approval_status: str = "n/a",
        screenshot_ref: str | None = None,
        error: str | None = None,
        extra: dict | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(UTC).isoformat(),
            user_command=redact_secrets(user_command or "") or None,
            agent=agent,
            model=model,
            tool=tool,
            input_summary=redact_secrets(input_summary)[:1000],
            output_summary=redact_secrets(output_summary)[:1000],
            risk=risk,
            approval_status=approval_status,
            screenshot_ref=screenshot_ref,
            error=redact_secrets(error) if error else None,
            extra=extra or {},
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]
            if self.sink_path:
                try:
                    with self.sink_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(asdict(entry)) + "\n")
                except OSError:
                    pass
        return entry

    def recent(self, limit: int = 100) -> list[AuditEntry]:
        with self._lock:
            return list(reversed(self._entries[-limit:]))

    def all(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries)
